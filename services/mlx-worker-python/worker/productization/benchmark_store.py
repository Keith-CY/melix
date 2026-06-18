from __future__ import annotations

import csv
import json
import math
import time
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import Any

from worker.productization.apple_silicon_telemetry import (
    AppleSiliconTelemetryCollector,
    NoOpAppleSiliconTelemetryCollector,
)
from worker.productization.benchmark_export import (
    _benchmark_compare_identity,
    _canonical_benchmark_request_columns,
    _canonical_benchmark_matrix_request_columns,
    _canonical_benchmark_matrix_summary_columns,
    _csv_value,
)
from worker.productization.benchmark_schemas import (
    BenchmarkMatrixJob,
    BenchmarkMatrixRequestRow,
    BenchmarkMatrixSummaryRow,
    ServingBenchmarkRequestRow,
    ServingBenchmarkJob,
    build_serving_benchmark_repeat_group_row,
    ServingBenchmarkResult,
    build_serving_benchmark_request_row,
)
from worker.trajectory_provenance import normalize_trajectory_provenance
from worker.productization.probe_policy import ProbePolicy
from worker.productization.run_evidence import (
    assert_valid_run_evidence_payload,
    build_serving_benchmark_run_evidence,
    monotonic_ms,
)
from worker.productization.run_records import (
    attach_run_record_write_probe,
    build_benchmark_matrix_run_record,
    build_serving_benchmark_run_record,
    write_run_record,
)


def _is_serving_text_request_context(row: dict[str, object]) -> bool:
    return (
        row.get("schema_version") == "melix.serving_benchmark_context_row.v1"
        and row.get("task_kind") == "text-generation"
        and bool(row.get("job_id"))
        and bool(row.get("model_id"))
        and bool(row.get("suite"))
    )


def _dict_value(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _object_tuple(value: object) -> tuple[object, ...]:
    return tuple(value) if isinstance(value, (list, tuple)) else ()


def _dict_float_mapping(value: object) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for key, raw_value in _dict_value(value).items():
        try:
            metrics[str(key)] = float(raw_value or 0.0)
        except (TypeError, ValueError):
            continue
    return metrics


def _float_value(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _optional_float_value(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_repeat_group_metric(value: float) -> float:
    return round(float(value), 4)


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _request_row_common_fields(
    row: dict[str, object],
    *,
    request_index: int,
) -> dict[str, object]:
    return {
        "job_id": str(row.get("job_id", "")),
        "model_id": str(row.get("model_id", "")),
        "task_kind": str(row.get("task_kind", "")),
        "source_repo": str(row.get("source_repo", "")),
        "suite": str(row.get("suite", "")),
        "context_length": _int_value(row.get("context_length", 0)),
        "generation_length": _int_value(row.get("generation_length", 0)),
        "batch_size": _int_value(row.get("batch_size", 0)),
        "repeat_index": _int_value(row.get("repeat_index", 0)),
        "request_index": request_index,
        "dataset_materialize_ms": _float_value(row.get("dataset_materialize_ms", 0.0)),
        "prompt_render_ms": _float_value(row.get("prompt_render_ms", 0.0)),
    }


class BenchmarkStore:
    def __init__(
        self,
        *,
        telemetry_collector: Any | None = None,
        probe_policy: ProbePolicy | None = None,
    ) -> None:
        self._probe_policy = probe_policy or ProbePolicy.from_env()
        self._telemetry_collector = telemetry_collector or self._default_telemetry_collector(
            self._probe_policy
        )

    def start_telemetry_session(self, *, run_id: str):
        return self._telemetry_collector.start_session(run_id=run_id)

    @staticmethod
    def _default_telemetry_collector(policy: ProbePolicy) -> Any:
        if policy.telemetry_enabled:
            return AppleSiliconTelemetryCollector()
        return NoOpAppleSiliconTelemetryCollector(reason=policy.no_op_reason)

    def persist_serving_benchmark(
        self,
        *,
        jobs_root: Path,
        job: ServingBenchmarkJob,
        results: tuple[ServingBenchmarkResult, ...],
        context_rows: Iterable[dict[str, object]] = (),
        batch_rows: Iterable[dict[str, object]] = (),
        request_rows: Iterable[ServingBenchmarkRequestRow] = (),
        telemetry_collection: Any | None = None,
        model_memory_summary: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        artifact_write_started_at_monotonic_ms = monotonic_ms()
        jobs_root.mkdir(parents=True, exist_ok=True)

        job_path = jobs_root / "bench-job.json"
        job_path.write_text(
            json.dumps(job.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

        persisted: dict[str, Path] = {"job": job_path}
        for result in results:
            result_path = jobs_root / f"bench-result-{result.suite}.json"
            result_path.write_text(
                json.dumps(result.to_dict(), indent=2) + "\n",
                encoding="utf-8",
            )
            persisted[result.suite] = result_path

        context_rows_tuple = tuple(context_rows)
        if context_rows_tuple:
            context_rows_path = jobs_root / "bench-context-rows.jsonl"
            self._write_jsonl(context_rows_path, context_rows_tuple)
            persisted["context_rows_jsonl"] = context_rows_path

        batch_rows_tuple = tuple(batch_rows)
        if batch_rows_tuple:
            batch_rows_path = jobs_root / "bench-batch-rows.jsonl"
            self._write_jsonl(batch_rows_path, batch_rows_tuple)
            persisted["batch_rows_jsonl"] = batch_rows_path

        repeat_group_rows = self._repeat_group_rows_from_benchmark_rows(
            context_rows=context_rows_tuple,
            batch_rows=batch_rows_tuple,
        )
        if repeat_group_rows:
            repeat_groups_path = jobs_root / "bench-repeat-groups.jsonl"
            self._write_jsonl(repeat_groups_path, repeat_group_rows)
            persisted["repeat_groups_jsonl"] = repeat_groups_path

        request_rows_tuple = tuple(request_rows)
        if not request_rows_tuple:
            request_rows_tuple = self._request_rows_from_context_rows(context_rows_tuple)
        if request_rows_tuple:
            request_rows_tuple = self._attach_request_compare_identity(
                job=job,
                request_rows=request_rows_tuple,
            )
        if request_rows_tuple:
            request_rows_jsonl_path = jobs_root / "bench-request-rows.jsonl"
            request_rows_csv_path = jobs_root / "bench-request-rows.csv"
            self._write_jsonl_and_csv(
                jsonl_path=request_rows_jsonl_path,
                csv_path=request_rows_csv_path,
                rows=request_rows_tuple,
                fieldnames=_canonical_benchmark_request_columns(),
            )
            persisted["request_rows_jsonl"] = request_rows_jsonl_path
            persisted["request_rows_csv"] = request_rows_csv_path

        if telemetry_collection is None:
            telemetry_collection = self._telemetry_collector.collect_completed_run(
                artifact_root=jobs_root,
                run_id=job.job_id,
                output_token_count=self._output_token_count(context_rows_tuple, batch_rows_tuple),
            )
        persisted["telemetry_jsonl"] = Path(telemetry_collection.artifact_path)

        evidence_path = jobs_root / "run-evidence.json"
        evidence = build_serving_benchmark_run_evidence(
            job=job,
            results=results,
            artifact_root=jobs_root,
            artifact_paths=persisted,
            artifact_write_started_at_monotonic_ms=artifact_write_started_at_monotonic_ms,
            artifact_write_duration_ms=monotonic_ms() - artifact_write_started_at_monotonic_ms,
            context_rows=context_rows_tuple,
            batch_rows=batch_rows_tuple,
            telemetry_summary=telemetry_collection.summary,
            telemetry_probes=telemetry_collection.probes,
            model_memory_summary=model_memory_summary,
        )
        evidence_payload = evidence.to_dict()
        assert_valid_run_evidence_payload(evidence_payload)
        evidence_path.write_text(
            json.dumps(evidence_payload, indent=2) + "\n",
            encoding="utf-8",
        )
        persisted["evidence"] = evidence_path

        record_started_at_monotonic_ms = monotonic_ms()
        record_path = jobs_root / "run-record.json"
        record_paths = {**persisted, "run_record": record_path}
        record = build_serving_benchmark_run_record(
            job=job,
            results=results,
            artifact_root=jobs_root,
            artifact_paths=record_paths,
        )
        write_run_record(
            record_path,
            attach_run_record_write_probe(
                record,
                duration_ms=monotonic_ms() - record_started_at_monotonic_ms,
            ),
        )
        persisted["run_record"] = record_path

        return persisted

    @staticmethod
    def _write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            write = handle.write
            dump_json = json.dumps
            for row in rows:
                write(dump_json(row) + "\n")

    @staticmethod
    def _repeat_group_rows_from_benchmark_rows(
        *,
        context_rows: tuple[dict[str, object], ...],
        batch_rows: tuple[dict[str, object], ...],
    ) -> tuple[dict[str, object], ...]:
        grouped: dict[tuple[object, ...], list[dict[str, object]]] = {}
        for source_row_kind, rows in (("context", context_rows), ("batch", batch_rows)):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                key = BenchmarkStore._repeat_group_key(row, source_row_kind=source_row_kind)
                if key is None:
                    continue
                grouped.setdefault(key, []).append(row)

        repeat_group_rows: list[dict[str, object]] = []
        for key in sorted(grouped):
            rows = grouped[key]
            if not rows:
                continue
            first = rows[0]
            source_row_kind = str(key[0])
            repetition_index = tuple(
                sorted({_int_value(row.get("repeat_index", 0)) for row in rows})
            )
            metric_fields = BenchmarkStore._repeat_group_metric_fields(rows)
            repeat_group_rows.append(
                build_serving_benchmark_repeat_group_row(
                    job_id=str(first.get("job_id", "")),
                    model_id=str(first.get("model_id", "")),
                    task_kind=str(first.get("task_kind", "")),
                    source_repo=str(first.get("source_repo", "")),
                    suite=str(first.get("suite", "")),
                    context_length=_int_value(first.get("context_length", 0)),
                    generation_length=_int_value(first.get("generation_length", 0)),
                    batch_size=_int_value(first.get("batch_size", 0)),
                    cache_profile=str(first.get("cache_profile", "")),
                    reasoning_mode=str(first.get("reasoning_mode", "")),
                    structured_output_mode=str(first.get("structured_output_mode", "")),
                    source_row_kind=source_row_kind,
                    repetition_index=repetition_index,
                    sample_count=len(repetition_index),
                    seed_strategy="runner_repeat_index",
                    **metric_fields,
                ).to_dict()
            )
        return tuple(repeat_group_rows)

    @staticmethod
    def _repeat_group_key(
        row: dict[str, object],
        *,
        source_row_kind: str,
    ) -> tuple[object, ...] | None:
        if not row.get("job_id") or not row.get("suite"):
            return None
        return (
            source_row_kind,
            str(row.get("job_id", "")),
            str(row.get("model_id", "")),
            str(row.get("task_kind", "")),
            str(row.get("source_repo", "")),
            str(row.get("suite", "")),
            _int_value(row.get("context_length", 0)),
            _int_value(row.get("generation_length", 0)),
            _int_value(row.get("batch_size", 0)),
            str(row.get("cache_profile", "")),
            str(row.get("reasoning_mode", "")),
            str(row.get("structured_output_mode", "")),
        )

    @staticmethod
    def _repeat_group_metric_fields(rows: list[dict[str, object]]) -> dict[str, float | None]:
        fields: dict[str, float | None] = {}
        for output_prefix, input_key in (
            ("throughput", "decode_tokens_per_second"),
            ("ttft_ms", "ttft_ms"),
            ("request_latency_ms", "request_latency_ms"),
            ("peak_memory_bytes", "peak_memory_bytes"),
            ("energy_joules", "energy_joules"),
        ):
            values_by_repeat: dict[int, list[float]] = {}
            for row in rows:
                value = _optional_float_value(row.get(input_key))
                if value is None:
                    continue
                repeat_index = _int_value(row.get("repeat_index", 0))
                values_by_repeat.setdefault(repeat_index, []).append(value)
            values = [
                sum(repeat_values) / len(repeat_values)
                for repeat_index, repeat_values in sorted(values_by_repeat.items())
                if repeat_values
            ]
            mean, stdev, ci95_low, ci95_high = BenchmarkStore._repeat_group_stats(values)
            if mean is None:
                continue
            fields[f"{output_prefix}_mean"] = mean
            fields[f"{output_prefix}_stdev"] = stdev
            fields[f"{output_prefix}_ci95_low"] = ci95_low
            fields[f"{output_prefix}_ci95_high"] = ci95_high
        return fields

    @staticmethod
    def _repeat_group_stats(values: list[float]) -> tuple[float | None, float | None, float | None, float | None]:
        if not values:
            return (None, None, None, None)
        mean = sum(values) / len(values)
        if len(values) == 1:
            return (
                _round_repeat_group_metric(mean),
                0.0,
                _round_repeat_group_metric(mean),
                _round_repeat_group_metric(mean),
            )
        variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        stdev = math.sqrt(variance)
        half_width = 1.96 * stdev / math.sqrt(len(values))
        return (
            _round_repeat_group_metric(mean),
            _round_repeat_group_metric(stdev),
            _round_repeat_group_metric(mean - half_width),
            _round_repeat_group_metric(mean + half_width),
        )

    @staticmethod
    def _output_token_count(
        context_rows: tuple[dict[str, object], ...],
        batch_rows: tuple[dict[str, object], ...],
    ) -> int:
        total = 0
        for row in (*context_rows, *batch_rows):
            try:
                total += int(row.get("generation_length", 0) or 0)
            except (TypeError, ValueError):
                continue
        return total

    @staticmethod
    def _request_rows_from_context_rows(
        context_rows: tuple[dict[str, object], ...],
    ) -> tuple[ServingBenchmarkRequestRow, ...]:
        if not context_rows:
            return ()
        rows: list[ServingBenchmarkRequestRow] = []
        request_index = 0
        for context_row in context_rows:
            if not isinstance(context_row, dict):
                continue
            if not _is_serving_text_request_context(context_row):
                continue
            metrics = _dict_float_mapping(context_row.get("agentic_tool_metrics"))
            calls = _object_tuple(context_row.get("agentic_tool_calls"))
            observations = _object_tuple(context_row.get("agentic_tool_observations"))
            tool_latency_total_ms = _float_value(metrics.get("agentic_tool.latency_ms", 0.0))
            call_count = sum(1 for call in calls if isinstance(call, dict))
            per_tool_latency_ms = (
                round(tool_latency_total_ms / max(call_count, 1), 6)
                if call_count
                else 0.0
            )
            created_at_unix_ms = int(time.time() * 1000)
            phase_index = 0
            for call_index, raw_call in enumerate(calls):
                if not isinstance(raw_call, dict):
                    continue
                call = raw_call
                raw_observation = observations[call_index] if call_index < len(observations) else {}
                observation = raw_observation if isinstance(raw_observation, dict) else {}
                payload = _dict_value(observation.get("payload"))
                observation_metrics = _dict_value(observation.get("metrics"))
                rows.append(
                    build_serving_benchmark_request_row(
                        **_request_row_common_fields(context_row, request_index=request_index),
                        phase="tool_turn",
                        phase_index=phase_index,
                        status=str(observation.get("status", "completed") or "completed"),
                        error_stage=str(payload.get("failure_stage", "")),
                        duration_ms=per_tool_latency_ms,
                        tool_call_id=str(call.get("id", "")),
                        tool_name=str(call.get("name", "")),
                        tool_arguments=_dict_value(call.get("arguments")),
                        tool_observation=observation,
                        tool_latency_ms=per_tool_latency_ms,
                        agentic_tool_metrics=metrics,
                        created_at_unix_ms=created_at_unix_ms + phase_index,
                        observation_bytes=_int_value(
                            observation_metrics.get("tool_observation.emitted_bytes", 0)
                        ),
                        trajectory_provenance=normalize_trajectory_provenance(context_row),
                    )
                )
                phase_index += 1

            rows.append(
                build_serving_benchmark_request_row(
                    **_request_row_common_fields(context_row, request_index=request_index),
                    phase="final_answer",
                    phase_index=phase_index,
                    status=str(context_row.get("status", "completed") or "completed"),
                    error_stage=str(context_row.get("error_stage", "")),
                    duration_ms=_float_value(context_row.get("request_latency_ms", 0.0)),
                    ttft_ms=_float_value(context_row.get("ttft_ms", 0.0)),
                    request_latency_ms=_float_value(context_row.get("request_latency_ms", 0.0)),
                    prefill_tokens_per_second=_float_value(
                        context_row.get("prefill_tokens_per_second", 0.0)
                    ),
                    decode_tokens_per_second=_float_value(
                        context_row.get("decode_tokens_per_second", 0.0)
                    ),
                    peak_memory_bytes=_float_value(context_row.get("peak_memory_bytes", 0.0)),
                    warmup_ms=_float_value(context_row.get("warmup_ms", 0.0)),
                    prefill_ms=_float_value(context_row.get("prefill_ms", 0.0)),
                    decode_ms=_float_value(context_row.get("decode_ms", 0.0)),
                    tokens_in=_int_value(context_row.get("tokens_in", 0)),
                    tokens_out=_int_value(context_row.get("tokens_out", 0)),
                    first_token_index=_int_value(context_row.get("first_token_index", 0)),
                    cache_hit=bool(context_row.get("cache_hit", False)),
                    runtime_kind=str(context_row.get("runtime_kind", "")),
                    agentic_tool_metrics=metrics,
                    created_at_unix_ms=created_at_unix_ms + phase_index,
                    trajectory_provenance=normalize_trajectory_provenance(context_row),
                )
            )
            request_index += 1
        return tuple(rows)

    @staticmethod
    def _attach_request_compare_identity(
        *,
        job: ServingBenchmarkJob,
        request_rows: tuple[ServingBenchmarkRequestRow, ...],
    ) -> tuple[ServingBenchmarkRequestRow, ...]:
        metadata = _benchmark_compare_identity(job.to_dict())
        metadata_is_adapter = metadata["compare_target_kind"] == "adapter"
        rows: list[ServingBenchmarkRequestRow] = []
        for row in (row for row in request_rows if isinstance(row, ServingBenchmarkRequestRow)):
            if not metadata_is_adapter:
                rows.append(
                    replace(
                        row,
                        compare_target_kind="base",
                        base_model_id=metadata["base_model_id"] or row.model_id,
                        adapter_manifest_path="",
                        adapter_set_hash="",
                        adapter_activation_mode="",
                    )
                )
                continue
            rows.append(
                replace(
                    row,
                    compare_target_kind=(
                        metadata["compare_target_kind"]
                        if row.compare_target_kind == "base"
                        else row.compare_target_kind or metadata["compare_target_kind"]
                    ),
                    base_model_id=(
                        metadata["base_model_id"]
                        if row.base_model_id == row.model_id
                        else row.base_model_id or metadata["base_model_id"]
                    ),
                    adapter_manifest_path=row.adapter_manifest_path
                    or metadata["adapter_manifest_path"],
                    adapter_set_hash=row.adapter_set_hash or metadata["adapter_set_hash"],
                    adapter_activation_mode=row.adapter_activation_mode
                    or metadata["adapter_activation_mode"],
                )
            )
        return tuple(rows)

    def persist_benchmark_matrix(
        self,
        *,
        jobs_root: Path,
        job: BenchmarkMatrixJob,
        summary_rows: tuple[BenchmarkMatrixSummaryRow, ...],
        request_rows: tuple[BenchmarkMatrixRequestRow, ...],
    ) -> dict[str, Path]:
        jobs_root.mkdir(parents=True, exist_ok=True)
        summary_rows = self._attach_matrix_tool_turn_summary_fields(
            summary_rows=summary_rows,
            request_rows=request_rows,
        )

        job_path = jobs_root / "bench-matrix-job.json"
        job_path.write_text(
            json.dumps(job.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

        summary_jsonl_path = jobs_root / "bench-matrix-summary.jsonl"
        summary_csv_path = jobs_root / "bench-matrix-summary.csv"
        self._write_jsonl_and_csv(
            jsonl_path=summary_jsonl_path,
            csv_path=summary_csv_path,
            rows=summary_rows,
            fieldnames=_canonical_benchmark_matrix_summary_columns(),
        )

        requests_jsonl_path = jobs_root / "bench-matrix-requests.jsonl"
        requests_csv_path = jobs_root / "bench-matrix-requests.csv"
        self._write_jsonl_and_csv(
            jsonl_path=requests_jsonl_path,
            csv_path=requests_csv_path,
            rows=request_rows,
            fieldnames=_canonical_benchmark_matrix_request_columns(),
        )

        persisted = {
            "job": job_path,
            "summary_jsonl": summary_jsonl_path,
            "summary_csv": summary_csv_path,
            "requests_jsonl": requests_jsonl_path,
            "requests_csv": requests_csv_path,
        }
        record_started_at_monotonic_ms = monotonic_ms()
        record_path = jobs_root / "run-record.json"
        record_paths = {**persisted, "run_record": record_path}
        record = build_benchmark_matrix_run_record(
            job=job,
            summary_rows=summary_rows,
            artifact_root=jobs_root,
            artifact_paths=record_paths,
        )
        write_run_record(
            record_path,
            attach_run_record_write_probe(
                record,
                duration_ms=monotonic_ms() - record_started_at_monotonic_ms,
            ),
        )
        persisted["run_record"] = record_path
        return persisted

    @staticmethod
    def _write_jsonl_and_csv(
        *,
        jsonl_path: Path,
        csv_path: Path,
        rows: Iterable[
            BenchmarkMatrixSummaryRow | BenchmarkMatrixRequestRow | ServingBenchmarkRequestRow
        ],
        fieldnames: list[str],
    ) -> None:
        with (
            jsonl_path.open("w", encoding="utf-8") as jsonl_handle,
            csv_path.open("w", encoding="utf-8", newline="") as csv_handle,
        ):
            csv_writer = csv.writer(csv_handle)
            csv_writer.writerow(fieldnames)
            write_jsonl = jsonl_handle.write
            dump_json = json.dumps
            normalize_csv_value = _csv_value
            def csv_rows() -> Iterable[list[str]]:
                for row in rows:
                    payload = row.to_dict()
                    write_jsonl(dump_json(payload) + "\n")
                    payload_get = payload.get
                    yield [normalize_csv_value(payload_get(field, "")) for field in fieldnames]

            csv_writer.writerows(csv_rows())

    @staticmethod
    def _attach_matrix_tool_turn_summary_fields(
        *,
        summary_rows: tuple[BenchmarkMatrixSummaryRow, ...],
        request_rows: tuple[BenchmarkMatrixRequestRow, ...],
    ) -> tuple[BenchmarkMatrixSummaryRow, ...]:
        if not summary_rows or not request_rows:
            return summary_rows
        if not all(isinstance(row, BenchmarkMatrixSummaryRow) for row in summary_rows):
            return summary_rows

        has_tool_turn_fields = False
        for row in request_rows:
            if not isinstance(row, BenchmarkMatrixRequestRow):
                return summary_rows
            if (
                row.tool_call_count
                or row.tool_latency_ms
                or row.observation_bytes
                or row.fatal_rate
                or row.turn_count
            ):
                has_tool_turn_fields = True
                break
        if not has_tool_turn_fields:
            return summary_rows

        aggregates_by_cell_key: dict[
            tuple[str, int, int, int, str, str, str, int],
            tuple[int, int, float, int, int, int],
        ] = {}
        for row in request_rows:
            key = (
                row.suite_id,
                row.context_length,
                row.generation_length,
                row.batch_size,
                row.cache_profile,
                row.reasoning_mode,
                row.structured_output_mode,
                row.concurrency_level,
            )
            (
                count,
                tool_call_count,
                tool_latency_ms,
                observation_bytes,
                fatal_count,
                turn_count,
            ) = aggregates_by_cell_key.get(key, (0, 0, 0.0, 0, 0, 0))
            aggregates_by_cell_key[key] = (
                count + 1,
                tool_call_count + row.tool_call_count,
                tool_latency_ms + row.tool_latency_ms,
                observation_bytes + row.observation_bytes,
                fatal_count + (1 if row.fatal_rate > 0.0 else 0),
                turn_count + row.turn_count,
            )

        hydrated_rows: list[BenchmarkMatrixSummaryRow] = []
        for row in summary_rows:
            if (
                row.tool_call_count
                or row.tool_latency_ms
                or row.observation_bytes
                or row.fatal_rate
                or row.turn_count
            ):
                hydrated_rows.append(row)
                continue
            aggregate = aggregates_by_cell_key.get(
                (
                    row.suite_id,
                    row.context_length,
                    row.generation_length,
                    row.batch_size,
                    row.cache_profile,
                    row.reasoning_mode,
                    row.structured_output_mode,
                    row.concurrency_level,
                )
            )
            if aggregate is None:
                hydrated_rows.append(row)
                continue
            (
                count,
                tool_call_count,
                tool_latency_ms,
                observation_bytes,
                fatal_count,
                turn_count,
            ) = aggregate
            if not (
                tool_call_count
                or tool_latency_ms
                or observation_bytes
                or fatal_count
                or turn_count
            ):
                hydrated_rows.append(row)
                continue
            hydrated_rows.append(
                replace(
                    row,
                    tool_call_count=tool_call_count,
                    tool_latency_ms=round(tool_latency_ms, 6),
                    observation_bytes=observation_bytes,
                    fatal_rate=round(fatal_count / max(count, 1), 6),
                    turn_count=turn_count,
                )
            )
        return tuple(hydrated_rows)
