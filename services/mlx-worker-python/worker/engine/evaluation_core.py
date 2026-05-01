from __future__ import annotations

import gc
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
import random
import re
import threading
import time
from typing import Any
from urllib.parse import urlparse

from packages.protocol.python.worker.v1 import common_pb2

_logger = logging.getLogger(__name__)
from worker.engine.code_eval_runner import (
    extract_candidate_code,
    is_code_execution_policy_supported,
    run_python_code_evaluation,
)
from worker.productization.benchmark_queue import BenchmarkQueueRecord, BenchmarkQueueStore
from worker.productization.evaluation_compare import (
    _DEFAULT_COMPARE_BOOTSTRAP_ITERATIONS,
    _DEFAULT_COMPARE_BOOTSTRAP_SEED,
    _DEFAULT_COMPARE_CONFIDENCE_LEVEL,
    _DEFAULT_COMPARE_EFFECT_THRESHOLD,
    AdapterTargetSpec,
    build_compare_samples,
    build_compare_summary,
    load_adapter_target_spec,
    parse_compare_target_adapter_manifest_paths,
    parse_compare_target_model_ids,
    resolve_compare_target_adapters,
    resolve_compare_target_models,
)
from worker.productization.evaluation_final_result import (
    EvaluationProfileDefinition,
    extract_final_result,
    score_final_result,
)
from worker.productization.event_extraction import (
    EventExtractionPromptSpec,
    RemoteEventExtractionTarget,
    RemoteSemanticJudgeTarget,
    SEMANTIC_JUDGE_PROMPT_HASH,
    RemoteProviderHTTPError,
    default_event_extraction_prompt_spec,
    evaluate_event_extraction,
    evaluate_event_extraction_semantic,
    event_prompt_content_hash,
    make_event_extraction_client,
    make_semantic_judge_client,
    normalize_event_fields,
    prompt_example_dialogue_ids,
    prompt_snapshot_payload,
)
from worker.productization.evaluation_schemas import (
    EvaluationCompareJob,
    EvaluationCompareSample,
    EvaluationCompareSummary,
    EvaluationCompareTargetLineage,
    EvaluationJob,
    EvaluationResult,
    EvaluationSample,
    build_evaluation_compare_job_record,
    build_evaluation_job_record,
    build_evaluation_result_record,
    build_evaluation_sample_record,
)
from worker.productization.evaluation_store import EvaluationStore


_SUITE_SCORE_MODES = {
    "mmlu": ("accuracy", "multiple_choice_accuracy"),
    "arc_challenge": ("accuracy", "multiple_choice_accuracy"),
    "hellaswag": ("accuracy", "multiple_choice_accuracy"),
    "winogrande": ("accuracy", "multiple_choice_accuracy"),
    "truthfulqa_mc": ("accuracy", "multiple_choice_accuracy"),
    "imagenette": ("accuracy", "exact_match"),
    "gsm8k": ("exact_match", "exact_match"),
    "humaneval": ("pass_at_1", "pass_at_1"),
    "mbpp": ("pass_at_1", "pass_at_1"),
}
_SUITE_SUPPORTED_SCORING_MODES = {
    "mmlu": {"multiple_choice_accuracy", "exact_match"},
    "arc_challenge": {"multiple_choice_accuracy", "exact_match"},
    "hellaswag": {"multiple_choice_accuracy", "exact_match"},
    "winogrande": {"multiple_choice_accuracy", "exact_match"},
    "truthfulqa_mc": {"multiple_choice_accuracy", "exact_match"},
    "imagenette": {"exact_match"},
    "gsm8k": {"exact_match"},
    "humaneval": {"pass_at_1"},
    "mbpp": {"pass_at_1"},
}
_CODE_EVAL_SUITES = {"humaneval", "mbpp"}
_CODE_EXEC_DISABLED_POLICIES = {"disabled", "forbidden"}
_CODE_EXEC_ENABLED_POLICIES = {"sandboxed"}
_ARITHMETIC_PROMPT_PATTERN = re.compile(r"\s*(\d+)\s*([+-])\s*(\d+)\s*\?\s*")
_ANSWER_PREFIX_PATTERN = re.compile(
    r"(?im)^\s*(?:final\s+answer|answer|the\s+answer\s+is|answer\s+is)\s*[:\-]?\s*(.+)$",
)
_NUMERIC_TOKEN_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")
_NUMERIC_RESULT_PATTERN = re.compile(r"=\s*([-+]?\d+(?:\.\d+)?)")
_OPTION_TOKEN_PATTERN = re.compile(r"\b([A-Z])\b")
_DIGIT_TOKEN_PATTERN = re.compile(r"\b(\d+)\b")
_MULTIMODAL_TASK_KINDS = {"image-to-text", "image-text-to-text"}
_SAMPLE_PROBE_MEAN_FIELDS = (
    ("sample_render_ms_mean", "sample_render_ms"),
    ("inference_ms_mean", "inference_ms"),
    ("extraction_ms_mean", "extraction_ms"),
    ("validation_ms_mean", "validation_ms"),
    ("scoring_ms_mean", "scoring_ms"),
    ("raw_response_chars_mean", "raw_response_chars"),
    ("extracted_result_chars_mean", "extracted_result_chars"),
)


@dataclass(frozen=True)
class EvaluationRun:
    job: EvaluationJob | EvaluationCompareJob
    results: tuple[EvaluationResult | EvaluationCompareSummary, ...]
    samples: tuple[EvaluationSample | EvaluationCompareSample, ...]
    persisted_paths: dict[str, Path]

    @property
    def result(self) -> EvaluationResult | EvaluationCompareSummary:
        return self.results[0]


@dataclass(frozen=True)
class SampleSummary:
    sample_count: int
    typed_score_mean: float
    extraction_success_count: int
    validation_success_count: int
    threshold_pass_count: int
    scored_sample_count: int
    failure_count: int
    extraction_success_rate: float
    validation_success_rate: float
    threshold_pass_rate: float
    code_exec_pass_count: int | None = None
    code_exec_fail_count: int | None = None


class EvaluationCore:
    def __init__(
        self,
        *,
        jobs_root: Path | None = None,
        store: EvaluationStore | None = None,
        queue_store: BenchmarkQueueStore | None = None,
        registry: Any | None = None,
    ) -> None:
        self._jobs_root = Path(jobs_root).resolve() if jobs_root is not None else None
        self._store = store or EvaluationStore()
        self._queue_store = queue_store or BenchmarkQueueStore()
        self._registry = registry
        self._job_id_lock = threading.Lock()
        self._next_job_index: int | None = None

    @staticmethod
    def _load_dataset_samples(
        samples_path: Path,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if limit is not None and limit <= 0:
            return []
        samples: list[dict[str, Any]] = []
        with samples_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                samples.append(json.loads(line))
                if limit is not None and len(samples) >= limit:
                    break
        return samples

    def run_local_suite(
        self,
        *,
        model_id: str,
        model_handle: str | None = None,
        suite_id: str,
        dataset_root: Path,
        sample_size: int,
        few_shot: int | None = None,
        seed: int | None = None,
        scoring_mode: str | None = None,
        code_exec_policy: str | None = None,
        parameters: dict[str, str] | None = None,
        remote_target: Any | None = None,
    ) -> EvaluationRun:
        requested_scoring_mode = (
            scoring_mode
            if scoring_mode is not None and scoring_mode != ""
            else (parameters or {}).get("scoring_mode", "")
        )
        if suite_id == "event_extraction" or requested_scoring_mode == "event_extraction_weighted_f1":
            return self._run_event_extraction_suite(
                model_id=model_id,
                suite_id=suite_id,
                dataset_id=(parameters or {}).get("dataset_id", ""),
                sample_size=sample_size,
                scoring_mode=requested_scoring_mode or "event_extraction_weighted_f1",
                parameters=dict(parameters or {}),
                remote_target=remote_target,
            )

        dataset_root = Path(dataset_root).resolve()
        manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
        if manifest["suite_id"] != suite_id:
            raise ValueError(
                f"Dataset suite mismatch: expected {suite_id}, found {manifest['suite_id']}"
            )

        score_name, default_scoring_mode = _SUITE_SCORE_MODES.get(
            suite_id,
            ("typed_score_mean", str(manifest.get("scoring_mode") or "normalized_exact_match")),
        )
        profile = EvaluationCore._profile_from_manifest(
            manifest,
            suite_id=suite_id,
            default_scoring_mode=default_scoring_mode,
        )
        if scoring_mode:
            profile = EvaluationProfileDefinition(
                profile_type=profile.profile_type,
                result_kind=profile.result_kind,
                extraction_mode=profile.extraction_mode,
                scoring_mode=scoring_mode,
                threshold=profile.threshold,
                output_schema=profile.output_schema,
                ignored_paths=profile.ignored_paths,
            )
        resolved_task_kind = str(
            (parameters or {}).get("task_kind") or manifest.get("task_kind") or "text-generation"
        )
        manifest_input_modalities = tuple(
            str(value)
            for value in manifest.get("input_modalities", [])
            if str(value).strip()
        )
        requested_few_shot = self._requested_parameter(
            explicit_value=few_shot,
            parameters=parameters,
            key="few_shot",
        )
        resolved_few_shot = self._resolve_int_parameter(
            explicit_value=few_shot,
            parameters=parameters,
            key="few_shot",
        )
        requested_seed = self._requested_parameter(
            explicit_value=seed,
            parameters=parameters,
            key="seed",
        )
        resolved_seed = self._resolve_int_parameter(
            explicit_value=seed,
            parameters=parameters,
            key="seed",
        )
        prefix_sample_limit = self._dataset_sample_load_limit(
            sample_size=sample_size,
            few_shot=resolved_few_shot,
            seed=resolved_seed,
        )
        samples = EvaluationCore._load_dataset_samples(
            dataset_root / "samples.jsonl",
            limit=prefix_sample_limit,
        )
        requested_scoring_mode = (
            scoring_mode
            if scoring_mode is not None and scoring_mode != ""
            else (parameters or {}).get("scoring_mode", "")
        )
        resolved_scoring_mode = self._resolve_scoring_mode(
            suite_id=suite_id,
            requested_scoring_mode=requested_scoring_mode,
            default_scoring_mode=default_scoring_mode,
        )
        profile = EvaluationProfileDefinition(
            profile_type=profile.profile_type,
            result_kind=profile.result_kind,
            extraction_mode=profile.extraction_mode,
            scoring_mode=resolved_scoring_mode,
            threshold=profile.threshold,
            output_schema=profile.output_schema,
            ignored_paths=profile.ignored_paths,
        )
        requested_code_exec_policy = (
            code_exec_policy
            if code_exec_policy is not None and code_exec_policy != ""
            else (parameters or {}).get("code_exec_policy", "")
        )
        resolved_code_exec_policy = self._resolve_code_exec_policy(
            suite_id=suite_id,
            requested_code_exec_policy=requested_code_exec_policy,
        )
        if resolved_code_exec_policy in _CODE_EXEC_ENABLED_POLICIES and not is_code_execution_policy_supported(
            resolved_code_exec_policy
        ):
            raise ValueError(
                f"code_exec_policy '{resolved_code_exec_policy}' is unavailable on this worker"
            )
        few_shot_examples, selected = self._plan_evaluation_samples(
            samples=samples,
            sample_size=sample_size,
            few_shot=resolved_few_shot,
            seed=resolved_seed,
        )
        created_at_unix_ms = int(time.time() * 1000)
        job_id = self._next_job_id()
        run_root = self._run_root(job_id)
        loaded_model = self._loaded_model_for_execution(model_handle)
        job_parameters = {"dataset_root": str(dataset_root)}
        if parameters:
            job_parameters.update(parameters)
        runtime_evidence = EvaluationCore._runtime_evidence_for_loaded_model(loaded_model)
        job_parameters.update(runtime_evidence)
        if EvaluationCore._truthy_parameter(job_parameters, "require_live_model"):
            EvaluationCore._validate_required_live_model(runtime_evidence, operation="evaluation")
        combined_samples = [*few_shot_examples, *selected]
        self._validate_task_kind_against_dataset(
            dataset_id=str(manifest["dataset_id"]),
            samples=combined_samples,
            manifest_input_modalities=manifest_input_modalities,
            task_kind=resolved_task_kind,
        )
        self._validate_live_multimodal_execution(
            loaded_model=loaded_model,
            manifest_input_modalities=manifest_input_modalities,
            samples=combined_samples,
            task_kind=resolved_task_kind,
        )
        resolved_model_id = (
            getattr(getattr(loaded_model, "spec", None), "model_id", "") if loaded_model is not None else ""
        ) or model_id
        job_parameters.setdefault("task_kind", resolved_task_kind)
        job_parameters["requested_few_shot"] = str(requested_few_shot)
        job_parameters["effective_few_shot"] = str(resolved_few_shot)
        job_parameters["few_shot"] = str(resolved_few_shot)
        job_parameters["requested_seed"] = str(requested_seed)
        job_parameters["effective_seed"] = str(resolved_seed)
        job_parameters["seed"] = str(resolved_seed)
        job_parameters["requested_scoring_mode"] = str(requested_scoring_mode)
        job_parameters["effective_scoring_mode"] = resolved_scoring_mode
        job_parameters["scoring_mode"] = resolved_scoring_mode
        job_parameters["requested_code_exec_policy"] = str(requested_code_exec_policy)
        job_parameters["effective_code_exec_policy"] = resolved_code_exec_policy
        job_parameters["code_exec_policy"] = resolved_code_exec_policy
        job_parameters.setdefault("profile_type", profile.profile_type)
        job_parameters.setdefault("result_kind", profile.result_kind)
        job_parameters.setdefault("extraction_mode", profile.extraction_mode)
        job_parameters.setdefault("threshold", str(profile.threshold))
        job_parameters.setdefault("ignored_paths", ",".join(profile.ignored_paths))
        if profile.output_schema:
            job_parameters.setdefault("output_schema", json.dumps(profile.output_schema, sort_keys=True))

        compare_mode = str(job_parameters.get("compare_mode", "")).strip()
        if compare_mode:
            return self._run_compare_suite(
                model_id=model_id,
                resolved_model_id=resolved_model_id,
                suite_id=suite_id,
                dataset_id=str(manifest["dataset_id"]),
                profile=profile,
                resolved_scoring_mode=resolved_scoring_mode,
                resolved_task_kind=resolved_task_kind,
                manifest_input_modalities=manifest_input_modalities,
                dataset_root=dataset_root,
                few_shot_examples=few_shot_examples,
                selected=selected,
                loaded_model=loaded_model,
                job_id=job_id,
                run_root=run_root,
                job_parameters=job_parameters,
                created_at_unix_ms=created_at_unix_ms,
                resolved_code_exec_policy=resolved_code_exec_policy,
                resolved_seed=resolved_seed,
            )

        started_at = time.perf_counter()
        sample_records = self._sample_records_for_model(
            job_id=job_id,
            suite_id=suite_id,
            dataset_id=manifest["dataset_id"],
            task_kind=resolved_task_kind,
            manifest_input_modalities=manifest_input_modalities,
            dataset_root=dataset_root,
            few_shot_examples=few_shot_examples,
            selected=selected,
            loaded_model=loaded_model,
            scoring_mode=resolved_scoring_mode,
            code_exec_policy=resolved_code_exec_policy,
            seed=resolved_seed,
            job_parameters=job_parameters,
            profile=profile,
        )
        duration_seconds = round(time.perf_counter() - started_at, 6)
        summary = self._summarize_sample_records(
            sample_records,
            threshold=profile.threshold,
            include_code_exec_metrics=suite_id in _CODE_EVAL_SUITES,
        )
        job_parameters.setdefault("sample_size", str(summary.sample_count))
        sample_probe_means = self._sample_probe_means(
            sample_records,
            tuple(field_name for _, field_name in _SAMPLE_PROBE_MEAN_FIELDS),
        )
        result_metrics = {
            f"eval.{suite_id}.typed_score_mean": summary.typed_score_mean,
            f"eval.{suite_id}.threshold_pass_rate": summary.threshold_pass_rate,
            f"eval.{suite_id}.extraction_success_rate": summary.extraction_success_rate,
            f"eval.{suite_id}.validation_success_rate": summary.validation_success_rate,
            f"eval.{suite_id}.extraction_success_count": float(summary.extraction_success_count),
            f"eval.{suite_id}.validation_success_count": float(summary.validation_success_count),
            f"eval.{suite_id}.scored_sample_count": float(summary.scored_sample_count),
            f"eval.{suite_id}.failure_count": float(summary.failure_count),
            f"eval.{suite_id}.duration_seconds": duration_seconds,
            **{
                f"eval.{suite_id}.{metric_name}": sample_probe_means[field_name]
                for metric_name, field_name in _SAMPLE_PROBE_MEAN_FIELDS
            },
        }
        result_units = {
            f"eval.{suite_id}.typed_score_mean": "ratio",
            f"eval.{suite_id}.threshold_pass_rate": "ratio",
            f"eval.{suite_id}.extraction_success_rate": "ratio",
            f"eval.{suite_id}.validation_success_rate": "ratio",
            f"eval.{suite_id}.extraction_success_count": "count",
            f"eval.{suite_id}.validation_success_count": "count",
            f"eval.{suite_id}.scored_sample_count": "count",
            f"eval.{suite_id}.failure_count": "count",
            f"eval.{suite_id}.duration_seconds": "s",
            f"eval.{suite_id}.sample_render_ms_mean": "ms",
            f"eval.{suite_id}.inference_ms_mean": "ms",
            f"eval.{suite_id}.extraction_ms_mean": "ms",
            f"eval.{suite_id}.validation_ms_mean": "ms",
            f"eval.{suite_id}.scoring_ms_mean": "ms",
            f"eval.{suite_id}.raw_response_chars_mean": "chars",
            f"eval.{suite_id}.extracted_result_chars_mean": "chars",
        }
        if summary.code_exec_pass_count is not None and summary.code_exec_fail_count is not None:
            result_metrics[f"eval.{suite_id}.code_exec_pass_count"] = float(summary.code_exec_pass_count)
            result_metrics[f"eval.{suite_id}.code_exec_fail_count"] = float(summary.code_exec_fail_count)
            result_units[f"eval.{suite_id}.code_exec_pass_count"] = "count"
            result_units[f"eval.{suite_id}.code_exec_fail_count"] = "count"

        report_path = self._result_path(run_root if self._jobs_root is not None else dataset_root)
        output_dir = str(run_root) if self._jobs_root is not None else str(dataset_root)
        job = build_evaluation_job_record(
            job_id=job_id,
            model_id=resolved_model_id,
            task_kind=job_parameters.get("task_kind", resolved_task_kind),
            source_repo=job_parameters.get("source_repo", ""),
            suite_id=suite_id,
            dataset_id=manifest["dataset_id"],
            sample_size=len(sample_records),
            scoring_mode=resolved_scoring_mode,
            few_shot=resolved_few_shot,
            seed=resolved_seed,
            code_exec_policy=resolved_code_exec_policy,
            parameters=job_parameters,
            status="completed",
            output_dir=output_dir,
            created_at_unix_ms=created_at_unix_ms,
            updated_at_unix_ms=created_at_unix_ms,
        )
        result = build_evaluation_result_record(
            job_id=job.job_id,
            suite_id=suite_id,
            dataset_id=manifest["dataset_id"],
            sample_size=len(sample_records),
            primary_score_name="typed_score_mean",
            primary_score_value=summary.typed_score_mean,
            extraction_success_count=summary.extraction_success_count,
            validation_success_count=summary.validation_success_count,
            scored_sample_count=summary.scored_sample_count,
            failure_count=summary.failure_count,
            duration_seconds=duration_seconds,
            metrics=result_metrics,
            report_path=str(report_path),
            units=result_units,
        )
        persisted_paths: dict[str, Path] = {}
        if self._jobs_root is not None:
            queue_root = self._jobs_root / "queue"
            queued_at = created_at_unix_ms
            self._queue_store.enqueue(
                queue_root=queue_root,
                record=BenchmarkQueueRecord(
                    queue_item_id=job.job_id,
                    job_kind="evaluation",
                    model_id=model_id,
                    suite_ids=(suite_id,),
                    parameters=job_parameters,
                    status="queued",
                    created_at_unix_ms=queued_at,
                    updated_at_unix_ms=queued_at,
                ),
            )
            self._queue_store.transition(
                queue_root=queue_root,
                queue_item_id=job.job_id,
                status="running",
                updated_at_unix_ms=queued_at + 1,
            )
            persisted_paths = self._store.persist_result(
                jobs_root=self._jobs_root,
                job=job,
                result=result,
                samples=sample_records,
            )
            self._queue_store.transition(
                queue_root=queue_root,
                queue_item_id=job.job_id,
                status="completed",
                updated_at_unix_ms=int(time.time() * 1000),
            )
        return EvaluationRun(job=job, results=(result,), samples=sample_records, persisted_paths=persisted_paths)

    def _run_event_extraction_suite(
        self,
        *,
        model_id: str,
        suite_id: str,
        dataset_id: str,
        sample_size: int,
        scoring_mode: str,
        parameters: dict[str, str],
        remote_target: Any | None,
    ) -> EvaluationRun:
        source_jsonl = parameters.get("event_source_jsonl") or parameters.get("evaluation_source_locator", "")
        if not source_jsonl:
            raise ValueError("event_extraction_weighted_f1 requires a local JSONL source.")
        if remote_target is None or not getattr(remote_target, "api_key", ""):
            raise ValueError("event_extraction_weighted_f1 requires a remote provider target.")

        created_at_unix_ms = int(time.time() * 1000)
        job_id = self._next_job_id()
        output_root = (
            self._jobs_root / "event-extraction" / job_id
            if self._jobs_root is not None
            else Path.cwd() / "event-extraction" / job_id
        )
        remote_model_id = str(getattr(remote_target, "model_id", "") or model_id)
        safe_model_name = re.sub(r"[^A-Za-z0-9._-]+", "_", remote_model_id).strip("_") or "remote-model"
        predictions_dir = output_root / "predictions"
        reports_dir = output_root / "reports" / safe_model_name
        predictions_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)
        prediction_path = predictions_dir / f"{safe_model_name}.jsonl"
        failure_path = predictions_dir / f"{safe_model_name}.failures.jsonl"
        gold_subset_path = output_root / "gold_subset.jsonl"
        summary_path = reports_dir / "event_eval_summary.json"
        details_path = reports_dir / "event_eval_details.jsonl"
        trace_path = reports_dir / "event_eval_dialogue_traces.jsonl"
        row_audit_path = reports_dir / "event_eval_row_audit.jsonl"
        semantic_summary_path = reports_dir / "event_eval_semantic_summary.json"
        semantic_details_path = reports_dir / "event_eval_semantic_details.jsonl"
        semantic_row_audit_path = reports_dir / "event_eval_semantic_row_audit.jsonl"
        judge_audit_path = reports_dir / "event_eval_judge_audit.jsonl"
        error_log_path = reports_dir / "event_eval_error.json"
        prompt_snapshot_path = output_root / "prompt_snapshot.json"

        rows = self._read_event_extraction_rows(Path(source_jsonl), sample_size=sample_size)
        self._write_jsonl_rows(gold_subset_path, rows)
        prompt_spec = self._event_extraction_prompt_spec(parameters)
        overlapping_examples = sorted(
            set(prompt_example_dialogue_ids(prompt_spec))
            & {str(row.get("dialogue_id") or "").strip() for row in rows}
        )
        if overlapping_examples:
            raise ValueError(
                "event extraction prompt examples overlap evaluation rows: "
                + ", ".join(overlapping_examples)
            )
        prompt_snapshot = prompt_snapshot_payload(prompt_spec)
        prompt_snapshot_path.write_text(
            json.dumps(prompt_snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        client = make_event_extraction_client(
            RemoteEventExtractionTarget(
                provider_kind=str(getattr(remote_target, "provider_kind", "")),
                base_url=str(getattr(remote_target, "base_url", "")),
                api_key=str(getattr(remote_target, "api_key", "")),
                model_id=remote_model_id,
                timeout_seconds=int(getattr(remote_target, "timeout_seconds", 0) or 60),
                extra_body=self._remote_provider_extra_body(parameters),
            ),
            prompt_spec=prompt_spec,
        )
        rate_limit_per_minute = int(getattr(remote_target, "rate_limit_per_minute", 0) or 0)
        min_interval_seconds = 60.0 / rate_limit_per_minute if rate_limit_per_minute > 0 else 0.0
        last_request_started = 0.0
        prediction_rows: list[dict[str, object]] = []
        failures: list[dict[str, object]] = []
        dialogue_traces: list[dict[str, object]] = []
        raw_response_dir = output_root / "raw-responses" / safe_model_name
        raw_response_dir.mkdir(parents=True, exist_ok=True)

        started_at = time.perf_counter()
        events_written = 0
        for line_number, row in enumerate(rows, start=1):
            row_started_at = time.perf_counter()
            dialogue_id = str(row.get("dialogue_id") or "")
            dialogue = self._dialogue_lines(row.get("dialogue"))
            throttle_sleep_ms = 0.0
            if min_interval_seconds > 0 and last_request_started > 0:
                elapsed = time.perf_counter() - last_request_started
                if elapsed < min_interval_seconds:
                    sleep_seconds = min_interval_seconds - elapsed
                    time.sleep(sleep_seconds)
                    throttle_sleep_ms = self._round_ms(sleep_seconds * 1_000.0)
            last_request_started = time.perf_counter()
            request_started_at = last_request_started
            request_duration_ms = 0.0
            try:
                client_result = client.extract_events(dialogue, dialogue_id=dialogue_id)
                request_duration_ms = self._round_ms((time.perf_counter() - request_started_at) * 1_000.0)
                extracted_events, raw_response = client_result
                raw_response_path = raw_response_dir / f"{line_number:04d}-{self._safe_path_component(dialogue_id)}.txt"
                raw_response_path.write_text(
                    raw_response,
                    encoding="utf-8",
                )
            except Exception as exc:  # noqa: BLE001
                request_duration_ms = self._round_ms((time.perf_counter() - request_started_at) * 1_000.0)
                failure_record = {
                    "dialogue_id": dialogue_id,
                    "line_number": line_number,
                    "event_index": None,
                    "reason": str(exc),
                }
                provider_error_code = self._event_extraction_provider_error_code(exc)
                if provider_error_code:
                    failure_record["code"] = provider_error_code
                failures.append(failure_record)
                should_abort = self._should_abort_event_extraction_on_provider_error(exc)
                dialogue_traces.append(
                    self._event_extraction_dialogue_trace(
                        dialogue_id=dialogue_id,
                        line_number=line_number,
                        status="aborted" if should_abort else "failed",
                        row_started_at=row_started_at,
                        throttle_sleep_ms=throttle_sleep_ms,
                        request_duration_ms=request_duration_ms,
                        normalization_duration_ms=0.0,
                        dialogue=dialogue,
                        request_body_bytes=0,
                        response_body_bytes=0,
                        raw_response="",
                        raw_response_path=None,
                        predicted_event_count=0,
                        normalized_event_count=0,
                        normalization_failure_count=0,
                        error_code=provider_error_code or None,
                        failure_reason=str(exc),
                        provider_usage={},
                    )
                )
                if should_abort:
                    self._write_jsonl_rows(prediction_path, prediction_rows)
                    self._write_jsonl_rows(failure_path, failures)
                    self._write_jsonl_rows(trace_path, dialogue_traces)
                    error_payload = self._event_extraction_error_payload(
                        exc=exc,
                        failure_record=failure_record,
                        remote_target=remote_target,
                        remote_model_id=remote_model_id,
                        output_root=output_root,
                        prediction_path=prediction_path,
                        failure_path=failure_path,
                        trace_path=trace_path,
                        rows_total=len(rows),
                        rows_attempted=line_number,
                        events_written=events_written,
                    )
                    error_log_path.write_text(
                        json.dumps(error_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    raise RuntimeError(
                        "event extraction aborted after remote provider "
                        f"HTTP {getattr(exc, 'status_code', 'error')}; "
                        f"error_log={error_log_path}"
                    ) from exc
                prediction_rows.append({"dialogue_id": dialogue_id, "dialogue": dialogue, "events": []})
                continue

            normalized_events: list[dict[str, object]] = []
            normalization_failure_count = 0
            normalization_started_at = time.perf_counter()
            for event_index, event in enumerate(extracted_events):
                try:
                    normalized_events.append(normalize_event_fields(event))
                    events_written += 1
                except Exception as exc:  # noqa: BLE001
                    normalization_failure_count += 1
                    failures.append(
                        {
                            "dialogue_id": dialogue_id,
                            "line_number": line_number,
                            "event_index": event_index,
                            "reason": str(exc),
                        }
                    )
            normalization_duration_ms = self._round_ms((time.perf_counter() - normalization_started_at) * 1_000.0)
            prediction_rows.append(
                {
                    "dialogue_id": dialogue_id,
                    "dialogue": dialogue,
                    "events": normalized_events,
                }
            )
            dialogue_traces.append(
                self._event_extraction_dialogue_trace(
                    dialogue_id=dialogue_id,
                    line_number=line_number,
                    status="ok",
                    row_started_at=row_started_at,
                    throttle_sleep_ms=throttle_sleep_ms,
                    request_duration_ms=request_duration_ms,
                    normalization_duration_ms=normalization_duration_ms,
                    dialogue=dialogue,
                    request_body_bytes=self._client_result_int(client_result, "request_body_bytes"),
                    response_body_bytes=self._client_result_int(client_result, "response_body_bytes"),
                    raw_response=raw_response,
                    raw_response_path=raw_response_path,
                    predicted_event_count=len(extracted_events),
                    normalized_event_count=len(normalized_events),
                    normalization_failure_count=normalization_failure_count,
                    error_code=None,
                    failure_reason=None,
                    provider_usage=self._client_result_provider_usage(client_result),
                )
            )

        self._write_jsonl_rows(trace_path, dialogue_traces)
        self._write_jsonl_rows(prediction_path, prediction_rows)
        self._write_jsonl_rows(failure_path, failures)
        summary = evaluate_event_extraction(
            gold_jsonl=gold_subset_path,
            pred_jsonl=prediction_path,
            summary_output=summary_path,
            details_output=details_path,
            row_audit_output=row_audit_path,
        )
        summary["dialogue_diagnostics"] = self._event_extraction_dialogue_diagnostics(dialogue_traces)
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        semantic_summary: dict[str, object] | None = None
        semantic_judge_target = self._semantic_judge_target(parameters)
        if semantic_judge_target is not None:
            semantic_summary = self._run_event_extraction_semantic_scoring(
                gold_subset_path=gold_subset_path,
                prediction_path=prediction_path,
                semantic_summary_path=semantic_summary_path,
                semantic_details_path=semantic_details_path,
                semantic_row_audit_path=semantic_row_audit_path,
                judge_audit_path=judge_audit_path,
                judge_target=semantic_judge_target,
                judge_remote_server_id=str(parameters.get("semantic_judge_remote_server_id") or "").strip(),
                judge_model_id=semantic_judge_target.model_id,
            )
        duration_seconds = round(time.perf_counter() - started_at, 6)
        overall_weighted_f1 = float(summary["summary"]["overall_weighted_f1"])
        events_evaluated = int(summary["summary"]["events_evaluated"])
        events_matched = int(summary["summary"]["events_matched"])
        events_unmatched_gold = int(summary["summary"]["events_unmatched_gold"])
        events_unmatched_pred = int(summary["summary"]["events_unmatched_pred"])
        field_metrics = summary["field_metrics"]

        job_parameters = dict(parameters)
        job_parameters.pop("api_key", None)
        job_parameters.pop("remote_api_key", None)
        job_parameters.pop("eval_prompt_system_prompt", None)
        job_parameters.pop("eval_prompt_examples_json", None)
        job_parameters.pop("semantic_judge_api_key", None)
        job_parameters.pop("semantic_judge_base_url", None)
        job_parameters["dataset_root"] = str(Path(source_jsonl).resolve())
        job_parameters["event_source_jsonl"] = str(Path(source_jsonl).resolve())
        job_parameters["prediction_jsonl"] = str(prediction_path)
        job_parameters["failure_jsonl"] = str(failure_path)
        job_parameters["event_eval_summary"] = str(summary_path)
        job_parameters["event_eval_details"] = str(details_path)
        job_parameters["event_eval_dialogue_traces"] = str(trace_path)
        job_parameters["event_eval_row_audit"] = str(row_audit_path)
        if semantic_judge_target is not None:
            job_parameters["event_eval_semantic_summary"] = str(semantic_summary_path)
            job_parameters["event_eval_semantic_details"] = str(semantic_details_path)
            job_parameters["event_eval_semantic_row_audit"] = str(semantic_row_audit_path)
            job_parameters["event_eval_judge_audit"] = str(judge_audit_path)
            job_parameters["semantic_judge_remote_server_id"] = str(
                parameters.get("semantic_judge_remote_server_id") or ""
            ).strip()
            job_parameters["semantic_judge_model_id"] = semantic_judge_target.model_id
            job_parameters["semantic_judge_prompt_hash"] = SEMANTIC_JUDGE_PROMPT_HASH
        job_parameters["prompt_snapshot"] = str(prompt_snapshot_path)
        job_parameters["prompt_id"] = prompt_spec.prompt_id
        job_parameters["prompt_revision_id"] = prompt_spec.revision_id
        job_parameters["prompt_content_hash"] = prompt_spec.content_hash
        job_parameters["prompt_example_dialogue_ids"] = ",".join(prompt_example_dialogue_ids(prompt_spec))
        job_parameters["effective_scoring_mode"] = "event_extraction_weighted_f1"
        job_parameters["scoring_mode"] = "event_extraction_weighted_f1"
        job_parameters.setdefault("remote_model_id", remote_model_id)

        result_metrics = {
            f"eval.{suite_id}.overall_weighted_f1": overall_weighted_f1,
            f"eval.{suite_id}.events_evaluated": float(events_evaluated),
            f"eval.{suite_id}.events_matched": float(events_matched),
            f"eval.{suite_id}.events_unmatched_gold": float(events_unmatched_gold),
            f"eval.{suite_id}.events_unmatched_pred": float(events_unmatched_pred),
            f"eval.{suite_id}.events_written": float(events_written),
            f"eval.{suite_id}.events_failed": float(len(failures)),
            f"eval.{suite_id}.duration_seconds": duration_seconds,
        }
        result_units = {
            f"eval.{suite_id}.overall_weighted_f1": "ratio",
            f"eval.{suite_id}.events_evaluated": "count",
            f"eval.{suite_id}.events_matched": "count",
            f"eval.{suite_id}.events_unmatched_gold": "count",
            f"eval.{suite_id}.events_unmatched_pred": "count",
            f"eval.{suite_id}.events_written": "count",
            f"eval.{suite_id}.events_failed": "count",
            f"eval.{suite_id}.duration_seconds": "s",
        }
        if isinstance(semantic_summary, dict):
            semantic_metric_name = f"eval.{suite_id}.semantic_overall_weighted_f1"
            result_metrics[semantic_metric_name] = float(semantic_summary.get("overall_weighted_f1", 0.0))
            result_units[semantic_metric_name] = "ratio"
            semantic_status = str(semantic_summary.get("status") or "")
            if semantic_status:
                job_parameters["semantic_judge_status"] = semantic_status
        if isinstance(field_metrics, dict):
            for field_name, values in field_metrics.items():
                if isinstance(values, dict):
                    metric_name = f"eval.{suite_id}.{field_name}_f1"
                    result_metrics[metric_name] = float(values.get("f1", 0.0))
                    result_units[metric_name] = "ratio"

        resolved_dataset_id = dataset_id or "top200"
        job = build_evaluation_job_record(
            job_id=job_id,
            model_id=remote_model_id,
            task_kind="text-generation",
            source_repo=job_parameters.get("source_repo", ""),
            suite_id=suite_id,
            dataset_id=resolved_dataset_id,
            sample_size=len(rows),
            scoring_mode="event_extraction_weighted_f1",
            parameters=job_parameters,
            status="completed",
            output_dir=str(output_root),
            created_at_unix_ms=created_at_unix_ms,
            updated_at_unix_ms=created_at_unix_ms,
        )
        result = build_evaluation_result_record(
            job_id=job.job_id,
            suite_id=suite_id,
            dataset_id=resolved_dataset_id,
            sample_size=len(rows),
            primary_score_name="overall_weighted_f1",
            primary_score_value=overall_weighted_f1,
            extraction_success_count=max(len(rows) - len(failures), 0),
            validation_success_count=events_matched,
            scored_sample_count=events_evaluated,
            failure_count=len(failures),
            duration_seconds=duration_seconds,
            metrics=result_metrics,
            report_path=str(summary_path),
            units=result_units,
        )
        persisted_paths: dict[str, Path] = {}
        if self._jobs_root is not None:
            queue_root = self._jobs_root / "queue"
            self._queue_store.enqueue(
                queue_root=queue_root,
                record=BenchmarkQueueRecord(
                    queue_item_id=job.job_id,
                    job_kind="evaluation",
                    model_id=remote_model_id,
                    suite_ids=(suite_id,),
                    parameters=job_parameters,
                    status="queued",
                    created_at_unix_ms=created_at_unix_ms,
                    updated_at_unix_ms=created_at_unix_ms,
                ),
            )
            self._queue_store.transition(
                queue_root=queue_root,
                queue_item_id=job.job_id,
                status="running",
                updated_at_unix_ms=created_at_unix_ms + 1,
            )
            persisted_paths = self._store.persist_result(
                jobs_root=self._jobs_root,
                job=job,
                result=result,
                samples=(),
            )
            self._queue_store.transition(
                queue_root=queue_root,
                queue_item_id=job.job_id,
                status="completed",
                updated_at_unix_ms=int(time.time() * 1000),
            )
        return EvaluationRun(job=job, results=(result,), samples=(), persisted_paths=persisted_paths)

    @staticmethod
    def _event_extraction_provider_error_code(exc: Exception) -> str:
        code = getattr(exc, "code", "")
        return str(code) if code else ""

    @staticmethod
    def _write_jsonl_rows(path: Path, rows: list[dict[str, object]]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    @staticmethod
    def _round_ms(value: float) -> float:
        return round(float(value), 4)

    @staticmethod
    def _client_result_int(client_result: Any, field_name: str) -> int:
        value = getattr(client_result, field_name, 0)
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return 0

    @staticmethod
    def _client_result_provider_usage(client_result: Any) -> dict[str, int]:
        provider_usage = getattr(client_result, "provider_usage", {})
        if not isinstance(provider_usage, dict):
            return {}
        normalized: dict[str, int] = {}
        for key, value in provider_usage.items():
            if not isinstance(key, str) or isinstance(value, bool):
                continue
            if isinstance(value, int):
                normalized[key] = value
            elif isinstance(value, float) and value.is_integer():
                normalized[key] = int(value)
        return normalized

    @classmethod
    def _event_extraction_dialogue_trace(
        cls,
        *,
        dialogue_id: str,
        line_number: int,
        status: str,
        row_started_at: float,
        throttle_sleep_ms: float,
        request_duration_ms: float,
        normalization_duration_ms: float,
        dialogue: list[str],
        request_body_bytes: int,
        response_body_bytes: int,
        raw_response: str,
        raw_response_path: Path | None,
        predicted_event_count: int,
        normalized_event_count: int,
        normalization_failure_count: int,
        error_code: str | None,
        failure_reason: str | None,
        provider_usage: dict[str, int],
    ) -> dict[str, object]:
        return {
            "dialogue_id": dialogue_id,
            "line_number": line_number,
            "status": status,
            "total_duration_ms": cls._round_ms((time.perf_counter() - row_started_at) * 1_000.0),
            "request_duration_ms": request_duration_ms,
            "throttle_sleep_ms": throttle_sleep_ms,
            "normalization_duration_ms": normalization_duration_ms,
            "dialogue_line_count": len(dialogue),
            "dialogue_char_count": sum(len(line) for line in dialogue),
            "request_body_bytes": request_body_bytes,
            "response_body_bytes": response_body_bytes,
            "raw_response_chars": len(raw_response),
            "raw_response_path": str(raw_response_path) if raw_response_path is not None else None,
            "predicted_event_count": predicted_event_count,
            "normalized_event_count": normalized_event_count,
            "normalization_failure_count": normalization_failure_count,
            "error_code": error_code,
            "failure_reason": failure_reason,
            "provider_usage": provider_usage,
        }

    @classmethod
    def _event_extraction_dialogue_diagnostics(cls, traces: list[dict[str, object]]) -> dict[str, object]:
        status_counts = {"ok": 0, "failed": 0, "aborted": 0}
        for trace in traces:
            status = trace.get("status")
            if isinstance(status, str) and status in status_counts:
                status_counts[status] += 1

        request_latencies = cls._numeric_trace_values(traces, "request_duration_ms")
        total_latencies = cls._numeric_trace_values(traces, "total_duration_ms")
        raw_response_chars = cls._numeric_trace_values(traces, "raw_response_chars")
        throttle_sleep_values = cls._numeric_trace_values(traces, "throttle_sleep_ms")
        provider_usage_totals: dict[str, int] = {}
        for trace in traces:
            usage = trace.get("provider_usage")
            if not isinstance(usage, dict):
                continue
            for key, value in usage.items():
                if not isinstance(key, str) or isinstance(value, bool):
                    continue
                if isinstance(value, int):
                    provider_usage_totals[key] = provider_usage_totals.get(key, 0) + value
                elif isinstance(value, float) and value.is_integer():
                    provider_usage_totals[key] = provider_usage_totals.get(key, 0) + int(value)

        slowest_dialogues = []
        for trace in sorted(
            traces,
            key=lambda item: float(item.get("total_duration_ms") or 0.0),
            reverse=True,
        )[:5]:
            slowest_dialogues.append(
                {
                    "dialogue_id": trace.get("dialogue_id", ""),
                    "line_number": trace.get("line_number", 0),
                    "duration_ms": trace.get("total_duration_ms", 0.0),
                    "status": trace.get("status", ""),
                }
            )

        return {
            "dialogue_status_counts": status_counts,
            "request_duration_ms": cls._latency_stats(request_latencies),
            "total_duration_ms": cls._latency_stats(total_latencies),
            "total_throttle_sleep_ms": cls._round_ms(sum(throttle_sleep_values)),
            "raw_response_chars": {
                "mean": cls._round_ms(sum(raw_response_chars) / len(raw_response_chars)) if raw_response_chars else 0.0,
                "max": cls._round_ms(max(raw_response_chars)) if raw_response_chars else 0.0,
            },
            "provider_usage_totals": provider_usage_totals,
            "slowest_dialogues": slowest_dialogues,
        }

    @staticmethod
    def _semantic_judge_target(parameters: dict[str, str]) -> RemoteSemanticJudgeTarget | None:
        remote_server_id = str(parameters.get("semantic_judge_remote_server_id") or "").strip()
        if not remote_server_id:
            return None
        return RemoteSemanticJudgeTarget(
            provider_kind=str(parameters.get("semantic_judge_provider_kind") or "").strip(),
            base_url=str(parameters.get("semantic_judge_base_url") or "").strip(),
            api_key=str(parameters.get("semantic_judge_api_key") or "").strip(),
            model_id=str(parameters.get("semantic_judge_model_id") or "").strip(),
            timeout_seconds=int(str(parameters.get("semantic_judge_timeout_seconds") or "60") or 60),
            rate_limit_per_minute=int(str(parameters.get("semantic_judge_rate_limit_per_minute") or "0") or 0),
        )

    @staticmethod
    def _run_event_extraction_semantic_scoring(
        *,
        gold_subset_path: Path,
        prediction_path: Path,
        semantic_summary_path: Path,
        semantic_details_path: Path,
        semantic_row_audit_path: Path,
        judge_audit_path: Path,
        judge_target: RemoteSemanticJudgeTarget,
        judge_remote_server_id: str,
        judge_model_id: str,
    ) -> dict[str, object]:
        try:
            judge = make_semantic_judge_client(judge_target)
            return evaluate_event_extraction_semantic(
                gold_jsonl=gold_subset_path,
                pred_jsonl=prediction_path,
                summary_output=semantic_summary_path,
                details_output=semantic_details_path,
                row_audit_output=semantic_row_audit_path,
                judge_audit_output=judge_audit_path,
                judge=judge,
                judge_remote_server_id=judge_remote_server_id,
                judge_model_id=judge_model_id,
            )
        except Exception as exc:  # noqa: BLE001
            semantic_summary = {
                "status": "failed",
                "scoring_mode": "event_extraction_semantic_weighted_f1",
                "base_scoring_mode": "event_extraction_weighted_f1",
                "overall_weighted_f1": 0.0,
                "summary": {
                    "overall_weighted_f1": 0.0,
                    "events_evaluated": 0,
                    "events_matched": 0,
                    "events_unmatched_gold": 0,
                    "events_unmatched_pred": 0,
                },
                "semantic_judge": {
                    "judge_remote_server_id": judge_remote_server_id,
                    "judge_model_id": judge_model_id,
                    "judge_prompt_hash": SEMANTIC_JUDGE_PROMPT_HASH,
                    "calls": 0,
                    "cache_hits": 0,
                    "failures": 1,
                    "error_code": "semantic_judge_setup_failed",
                    "failure_reason": str(exc),
                },
            }
            semantic_summary_path.write_text(
                json.dumps(semantic_summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            EvaluationCore._write_jsonl_rows(semantic_details_path, [])
            EvaluationCore._write_jsonl_rows(semantic_row_audit_path, [])
            EvaluationCore._write_jsonl_rows(
                judge_audit_path,
                [
                    {
                        "status": "failed",
                        "source": "setup",
                        "error_code": "semantic_judge_setup_failed",
                        "failure_reason": str(exc),
                    }
                ],
            )
            return semantic_summary

    @staticmethod
    def _numeric_trace_values(traces: list[dict[str, object]], field_name: str) -> list[float]:
        values: list[float] = []
        for trace in traces:
            value = trace.get(field_name)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                values.append(float(value))
        return values

    @classmethod
    def _latency_stats(cls, values: list[float]) -> dict[str, float]:
        if not values:
            return {"mean": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
        return {
            "mean": cls._round_ms(sum(values) / len(values)),
            "p50": cls._round_ms(cls._percentile(values, 50.0)),
            "p95": cls._round_ms(cls._percentile(values, 95.0)),
            "max": cls._round_ms(max(values)),
        }

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        sorted_values = sorted(values)
        if len(sorted_values) == 1:
            return sorted_values[0]
        index = (len(sorted_values) - 1) * (percentile / 100.0)
        lower = int(index)
        upper = min(lower + 1, len(sorted_values) - 1)
        fraction = index - lower
        return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction

    @staticmethod
    def _should_abort_event_extraction_on_provider_error(exc: Exception) -> bool:
        if not isinstance(exc, RemoteProviderHTTPError):
            return False
        return exc.status_code in {401, 403, 404, 429} or exc.status_code >= 500

    @staticmethod
    def _event_extraction_error_payload(
        *,
        exc: Exception,
        failure_record: dict[str, object],
        remote_target: Any,
        remote_model_id: str,
        output_root: Path,
        prediction_path: Path,
        failure_path: Path,
        trace_path: Path,
        rows_total: int,
        rows_attempted: int,
        events_written: int,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "code": EvaluationCore._event_extraction_provider_error_code(exc) or "remote_provider_error",
            "message": str(exc),
            "remote_server_id": str(getattr(remote_target, "remote_server_id", "") or ""),
            "provider_kind": str(getattr(remote_target, "provider_kind", "") or ""),
            "remote_model_id": remote_model_id,
            "dialogue_id": failure_record.get("dialogue_id", ""),
            "line_number": failure_record.get("line_number", 0),
            "rows_total": rows_total,
            "rows_attempted": rows_attempted,
            "events_written": events_written,
            "output_dir": str(output_root),
            "prediction_jsonl": str(prediction_path),
            "failure_jsonl": str(failure_path),
            "event_eval_dialogue_traces": str(trace_path),
        }
        status_code = getattr(exc, "status_code", None)
        if status_code is not None:
            payload["status_code"] = int(status_code)
        response_body = str(getattr(exc, "response_body", "") or "")
        if response_body:
            payload["provider_response_excerpt"] = response_body[:2048]
        return payload

    def _run_compare_suite(
        self,
        *,
        model_id: str,
        resolved_model_id: str,
        suite_id: str,
        dataset_id: str,
        profile: EvaluationProfileDefinition,
        resolved_scoring_mode: str,
        resolved_task_kind: str,
        manifest_input_modalities: tuple[str, ...],
        dataset_root: Path,
        few_shot_examples: tuple[dict[str, object], ...],
        selected: list[dict[str, object]],
        loaded_model,
        job_id: str,
        run_root: Path,
        job_parameters: dict[str, str],
        created_at_unix_ms: int,
        resolved_code_exec_policy: str,
        resolved_seed: int,
    ) -> EvaluationRun:
        target_model_ids = parse_compare_target_model_ids(job_parameters)
        adapter_manifest_paths = parse_compare_target_adapter_manifest_paths(job_parameters)
        if not target_model_ids and not adapter_manifest_paths:
            raise ValueError(
                "evaluation compare requires at least one target — pass "
                "compare_target_model_ids and/or compare_target_adapter_manifest_paths."
            )
        adapter_target_specs: tuple[AdapterTargetSpec, ...] = tuple(
            load_adapter_target_spec(manifest_path=path, job_id=job_id)
            for path in adapter_manifest_paths
        )
        registered_targets = resolve_compare_target_models(
            registry=self._registry,
            target_model_ids=target_model_ids,
        )
        ephemeral_targets, ephemeral_unload_handles = resolve_compare_target_adapters(
            registry=self._registry,
            adapter_target_specs=adapter_target_specs,
        )
        try:
            return self._execute_compare_suite(
                model_id=model_id,
                resolved_model_id=resolved_model_id,
                suite_id=suite_id,
                dataset_id=dataset_id,
                profile=profile,
                resolved_scoring_mode=resolved_scoring_mode,
                resolved_task_kind=resolved_task_kind,
                manifest_input_modalities=manifest_input_modalities,
                dataset_root=dataset_root,
                few_shot_examples=few_shot_examples,
                selected=selected,
                loaded_model=loaded_model,
                job_id=job_id,
                run_root=run_root,
                job_parameters=job_parameters,
                created_at_unix_ms=created_at_unix_ms,
                resolved_code_exec_policy=resolved_code_exec_policy,
                resolved_seed=resolved_seed,
                target_model_ids=target_model_ids,
                registered_targets=registered_targets,
                adapter_target_specs=adapter_target_specs,
                ephemeral_targets=ephemeral_targets,
            )
        finally:
            # Unload every ephemeral adapter target the resolver handed us.
            # ``resolve_compare_target_adapters`` refuses to return an empty
            # handle (raises at load time instead), so every entry in
            # ``ephemeral_unload_handles`` is expected to be a non-empty
            # registry handle. Unload is best-effort: per-handle failures
            # are logged so operators have visibility without shadowing
            # the real compare error (if any) that surfaces from the try
            # block.
            for handle in ephemeral_unload_handles:
                if self._registry is None:
                    continue
                try:
                    self._registry.unload_model(handle)
                except Exception as unload_exc:  # noqa: BLE001
                    _logger.warning(
                        "Failed to unload ephemeral adapter compare target "
                        "(handle=%s): %s",
                        handle, unload_exc,
                    )

    def _execute_compare_suite(
        self,
        *,
        model_id: str,
        resolved_model_id: str,
        suite_id: str,
        dataset_id: str,
        profile: EvaluationProfileDefinition,
        resolved_scoring_mode: str,
        resolved_task_kind: str,
        manifest_input_modalities: tuple[str, ...],
        dataset_root: Path,
        few_shot_examples: tuple[dict[str, object], ...],
        selected: list[dict[str, object]],
        loaded_model,
        job_id: str,
        run_root: Path,
        job_parameters: dict[str, str],
        created_at_unix_ms: int,
        resolved_code_exec_policy: str,
        resolved_seed: int,
        target_model_ids: tuple[str, ...],
        registered_targets: dict[str, Any],
        adapter_target_specs: tuple[AdapterTargetSpec, ...],
        ephemeral_targets: dict[str, Any],
    ) -> EvaluationRun:
        # Flatten registered + ephemeral adapter targets into a single
        # ordered mapping; the compare loop treats them identically.
        target_models: dict[str, Any] = {**registered_targets, **ephemeral_targets}
        combined_target_ids: tuple[str, ...] = (
            target_model_ids
            + tuple(spec.ephemeral_derived_model_id for spec in adapter_target_specs)
        )
        for target_model in target_models.values():
            self._validate_live_multimodal_execution(
                loaded_model=target_model,
                manifest_input_modalities=manifest_input_modalities,
                samples=selected,
                task_kind=resolved_task_kind,
            )

        started_at = time.perf_counter()
        base_samples = self._sample_records_for_model(
            job_id=job_id,
            suite_id=suite_id,
            dataset_id=dataset_id,
            task_kind=resolved_task_kind,
            manifest_input_modalities=manifest_input_modalities,
            dataset_root=dataset_root,
            few_shot_examples=few_shot_examples,
            selected=selected,
            profile=profile,
            loaded_model=loaded_model,
            scoring_mode=resolved_scoring_mode,
            code_exec_policy=resolved_code_exec_policy,
            seed=resolved_seed,
            job_parameters=job_parameters,
            request_label=f"base:{resolved_model_id}",
        )
        compare_samples: list[EvaluationCompareSample] = []
        compare_summaries: list[EvaluationCompareSummary] = []
        report_path = run_root / "evaluation-compare-report.md" if self._jobs_root is not None else dataset_root / "evaluation-compare-report.md"
        for target_model_id in combined_target_ids:
            target_loaded_model = target_models[target_model_id]
            target_samples = self._sample_records_for_model(
                job_id=job_id,
                suite_id=suite_id,
                dataset_id=dataset_id,
                task_kind=resolved_task_kind,
                manifest_input_modalities=manifest_input_modalities,
                dataset_root=dataset_root,
                few_shot_examples=few_shot_examples,
                selected=selected,
                profile=profile,
                loaded_model=target_loaded_model,
                scoring_mode=resolved_scoring_mode,
                code_exec_policy=resolved_code_exec_policy,
                seed=resolved_seed,
                job_parameters=job_parameters,
                request_label=f"target:{target_model_id}",
            )
            target_compare_samples = build_compare_samples(
                job_id=job_id,
                suite_id=suite_id,
                dataset_id=dataset_id,
                target_model_id=target_model_id,
                threshold=profile.threshold,
                base_samples=base_samples,
                target_samples=target_samples,
            )
            compare_samples.extend(target_compare_samples)
            compare_summaries.append(
                build_compare_summary(
                    job_id=job_id,
                    base_model_id=resolved_model_id,
                    target_model_id=target_model_id,
                    suite_id=suite_id,
                    dataset_id=dataset_id,
                    sample_size=len(base_samples),
                    scoring_mode=resolved_scoring_mode,
                    threshold=profile.threshold,
                    base_samples=base_samples,
                    compare_samples=target_compare_samples,
                    effect_threshold=self._resolve_float_parameter(
                        parameters=job_parameters,
                        key="effect_threshold",
                        default_value=_DEFAULT_COMPARE_EFFECT_THRESHOLD,
                    ),
                    confidence_level=self._resolve_float_parameter(
                        parameters=job_parameters,
                        key="confidence_level",
                        default_value=_DEFAULT_COMPARE_CONFIDENCE_LEVEL,
                    ),
                    bootstrap_iterations=self._resolve_int_parameter(
                        explicit_value=None,
                        parameters=job_parameters,
                        key="bootstrap_iterations",
                    )
                    or _DEFAULT_COMPARE_BOOTSTRAP_ITERATIONS,
                    bootstrap_seed=self._resolve_int_parameter(
                        explicit_value=None,
                        parameters=job_parameters,
                        key="bootstrap_seed",
                    )
                    or _DEFAULT_COMPARE_BOOTSTRAP_SEED,
                    duration_seconds=round(time.perf_counter() - started_at, 6),
                    report_path=str(report_path),
                )
            )

        compare_job_parameters = dict(job_parameters)
        compare_job_parameters.setdefault("sample_size", str(len(base_samples)))
        output_dir = str(run_root) if self._jobs_root is not None else str(dataset_root)
        # Module 2 — assemble per-target lineage so exports preserve which
        # adapter produced which target column. Registered targets flow
        # through with empty adapter fields; adapter targets record the
        # full provenance.
        target_lineage_entries: list[EvaluationCompareTargetLineage] = [
            EvaluationCompareTargetLineage(
                target_model_id=target_model_id,
                materialization_kind="registered",
            )
            for target_model_id in target_model_ids
        ]
        for adapter_spec in adapter_target_specs:
            target_lineage_entries.append(
                EvaluationCompareTargetLineage(
                    target_model_id=adapter_spec.ephemeral_derived_model_id,
                    materialization_kind="ephemeral_adapter",
                    adapter_manifest_path=adapter_spec.manifest_path,
                    adapter_weights_path=adapter_spec.adapter_weights_path,
                    adapter_set_hash=adapter_spec.adapter_set_hash,
                    derived_from_model_id=adapter_spec.derived_from_model_id,
                )
            )
        compare_job = build_evaluation_compare_job_record(
            job_id=job_id,
            base_model_id=resolved_model_id,
            target_model_ids=combined_target_ids,
            target_lineage=tuple(target_lineage_entries),
            task_kind=compare_job_parameters.get("task_kind", resolved_task_kind),
            source_repo=compare_job_parameters.get("source_repo", ""),
            suite_id=suite_id,
            dataset_id=dataset_id,
            sample_size=len(base_samples),
            scoring_mode=resolved_scoring_mode,
            parameters=compare_job_parameters,
            status="completed",
            output_dir=output_dir,
            created_at_unix_ms=created_at_unix_ms,
            updated_at_unix_ms=created_at_unix_ms,
        )
        persisted_paths: dict[str, Path] = {}
        if self._jobs_root is not None:
            queue_root = self._jobs_root / "queue"
            queued_at = created_at_unix_ms
            self._queue_store.enqueue(
                queue_root=queue_root,
                record=BenchmarkQueueRecord(
                    queue_item_id=compare_job.job_id,
                    job_kind="evaluation",
                    model_id=model_id,
                    suite_ids=(suite_id,),
                    parameters=compare_job_parameters,
                    status="queued",
                    created_at_unix_ms=queued_at,
                    updated_at_unix_ms=queued_at,
                ),
            )
            self._queue_store.transition(
                queue_root=queue_root,
                queue_item_id=compare_job.job_id,
                status="running",
                updated_at_unix_ms=queued_at + 1,
            )
            persisted_paths = self._store.persist_compare_result(
                jobs_root=self._jobs_root,
                job=compare_job,
                summaries=tuple(compare_summaries),
                samples=tuple(compare_samples),
            )
            self._queue_store.transition(
                queue_root=queue_root,
                queue_item_id=compare_job.job_id,
                status="completed",
                updated_at_unix_ms=int(time.time() * 1000),
            )
        return EvaluationRun(
            job=compare_job,
            results=tuple(compare_summaries),
            samples=tuple(compare_samples),
            persisted_paths=persisted_paths,
        )

    def _sample_records_for_model(
        self,
        *,
        job_id: str,
        suite_id: str,
        dataset_id: str,
        task_kind: str,
        manifest_input_modalities: tuple[str, ...],
        dataset_root: Path,
        few_shot_examples: tuple[dict[str, object], ...],
        selected: list[dict[str, object]],
        profile: EvaluationProfileDefinition,
        loaded_model,
        scoring_mode: str,
        code_exec_policy: str,
        seed: int,
        job_parameters: dict[str, str],
        request_label: str = "",
    ) -> tuple[EvaluationSample, ...]:
        sample_records_list: list[EvaluationSample] = []
        for index, sample in enumerate(selected, start=1):
            sample_records_list.append(
                self._build_sample_record(
                    job_id=job_id,
                    suite_id=suite_id,
                    dataset_id=dataset_id,
                    task_kind=task_kind,
                    manifest_input_modalities=manifest_input_modalities,
                    dataset_root=dataset_root,
                    few_shot_examples=few_shot_examples,
                    index=index,
                    sample=sample,
                    profile=profile,
                    loaded_model=loaded_model,
                    scoring_mode=scoring_mode,
                    code_exec_policy=code_exec_policy,
                    seed=seed,
                    job_parameters=job_parameters,
                    request_label=request_label,
                )
            )
            if loaded_model is not None:
                self._release_runtime_memory()
        return tuple(sample_records_list)

    def _result_path(self, run_root: Path) -> Path:
        if self._jobs_root is not None:
            return run_root / "evaluation-result.json"
        return run_root / "evaluation-result.json"

    @staticmethod
    def _read_event_extraction_rows(path: Path, *, sample_size: int) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        with Path(path).open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"expected JSON object at {path}:{line_number}")
                if not isinstance(row.get("dialogue_id"), str) or not row.get("dialogue_id"):
                    raise ValueError(f"missing dialogue_id at {path}:{line_number}")
                if not isinstance(row.get("events"), list):
                    raise ValueError(f"events must be a list at {path}:{line_number}")
                normalized = dict(row)
                normalized["dialogue"] = EvaluationCore._dialogue_lines(row.get("dialogue"))
                rows.append(normalized)
                if sample_size > 0 and len(rows) >= sample_size:
                    break
        if not rows:
            raise ValueError(f"event extraction source JSONL is empty: {path}")
        return rows

    @staticmethod
    def _event_extraction_prompt_spec(parameters: dict[str, str]) -> EventExtractionPromptSpec:
        system_prompt = str(parameters.get("eval_prompt_system_prompt") or "").strip()
        if not system_prompt:
            return default_event_extraction_prompt_spec()

        examples_json = str(parameters.get("eval_prompt_examples_json") or "[]").strip() or "[]"
        try:
            parsed_examples = json.loads(examples_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"eval_prompt_examples_json must be valid JSON: {exc}") from exc
        if not isinstance(parsed_examples, list):
            raise ValueError("eval_prompt_examples_json must be a JSON array")
        examples: list[dict[str, object]] = []
        for index, example in enumerate(parsed_examples):
            if not isinstance(example, dict):
                raise ValueError(f"eval prompt example {index} must be a JSON object")
            dialogue_id = str(example.get("dialogue_id") or "").strip()
            if not dialogue_id:
                raise ValueError(f"eval prompt example {index} is missing dialogue_id")
            examples.append(example)

        prompt_id = str(parameters.get("eval_prompt_id") or parameters.get("prompt_id") or "").strip()
        revision_id = str(
            parameters.get("eval_prompt_revision_id") or parameters.get("prompt_revision_id") or ""
        ).strip()
        content_hash = str(
            parameters.get("eval_prompt_content_hash") or parameters.get("prompt_content_hash") or ""
        ).strip()
        if not content_hash:
            content_hash = event_prompt_content_hash(system_prompt, examples)
        return EventExtractionPromptSpec(
            prompt_id=prompt_id or "custom.event-extraction.prompt",
            revision_id=revision_id or "unknown",
            title=str(parameters.get("eval_prompt_title") or parameters.get("prompt_title") or "").strip(),
            system_prompt=system_prompt,
            examples=tuple(examples),
            content_hash=content_hash,
        )

    @staticmethod
    def _remote_provider_extra_body(parameters: dict[str, str]) -> dict[str, object]:
        raw_value = str(parameters.get("remote_provider_extra_body_json") or "").strip()
        if not raw_value:
            return {}
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"remote_provider_extra_body_json must be valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("remote_provider_extra_body_json must be a JSON object")
        return parsed

    @staticmethod
    def _dialogue_lines(value: object) -> list[str]:
        if isinstance(value, list):
            return [item.strip() for item in value if isinstance(item, str) and item.strip()]
        if isinstance(value, str):
            return [line.strip() for line in value.splitlines() if line.strip()]
        return []

    @staticmethod
    def _safe_path_component(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "dialogue"

    def _next_job_id(self) -> str:
        if self._jobs_root is None:
            return "eval-local"
        runs_root = self._jobs_root / "runs"
        runs_root.mkdir(parents=True, exist_ok=True)
        with self._job_id_lock:
            next_index = self._prime_next_job_index(runs_root)
            while True:
                job_id = f"eval-{next_index:04d}"
                try:
                    (runs_root / job_id).mkdir(parents=False, exist_ok=False)
                    self._next_job_index = next_index + 1
                    return job_id
                except FileExistsError:
                    next_index += 1
                    self._next_job_index = next_index

    @staticmethod
    def _parse_run_directory_index(name: str) -> int | None:
        if not name.startswith("eval-"):
            return None
        suffix = name[5:]
        if len(suffix) < 4 or not suffix.isdecimal():
            return None
        return int(suffix)

    def _prime_next_job_index(self, runs_root: Path) -> int:
        if self._next_job_index is not None:
            return self._next_job_index
        highest_index = 0
        with os.scandir(os.fspath(runs_root)) as entries:
            for entry in entries:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                index = self._parse_run_directory_index(entry.name)
                if index is None:
                    continue
                highest_index = max(highest_index, index)
        self._next_job_index = highest_index + 1
        return self._next_job_index

    def _run_root(self, job_id: str) -> Path:
        if self._jobs_root is None:
            return Path.cwd()
        return self._jobs_root / "runs" / job_id

    def _loaded_model_for_execution(self, model_handle: str | None):
        if not model_handle or self._registry is None:
            return None
        return self._registry.get_loaded_model(model_handle)

    @staticmethod
    def _truthy_parameter(parameters: dict[str, str], key: str) -> bool:
        raw_value = parameters.get(key, parameters.get(f"melix.{key}", ""))
        return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _runtime_evidence_for_loaded_model(loaded_model) -> dict[str, str]:
        if loaded_model is None:
            return {
                "runtime_live_model": "false",
                "runtime_model_handle": "",
                "runtime_kind": "",
                "runtime_name": "",
                "runtime_model_id": "",
                "runtime_model_path": "",
                "runtime_source_kind": "",
                "runtime_source_repo": "",
            }

        spec = getattr(loaded_model, "spec", None)
        runtime = getattr(loaded_model, "runtime", None)
        runtime_name = str(getattr(runtime, "runtime_name", "") or "")
        runtime_kind = str(getattr(loaded_model, "runtime_kind", "") or "")
        model_id = str(getattr(spec, "model_id", "") or "")
        model_path = str(getattr(spec, "model_path", "") or "")
        ext = getattr(spec, "ext", {}) if spec is not None else {}
        source_kind = str(ext.get("melix.source_kind", "") if hasattr(ext, "get") else "")
        source_repo = str(
            ext.get("melix.hf_repo_id", "")
            or ext.get("melix.source_repo", "")
            or ext.get("melix.model_path", "")
            if hasattr(ext, "get")
            else ""
        )
        live_model = EvaluationCore._runtime_name_is_live(runtime_name)
        return {
            "runtime_live_model": "true" if live_model else "false",
            "runtime_model_handle": str(getattr(loaded_model, "handle", "") or ""),
            "runtime_kind": runtime_kind,
            "runtime_name": runtime_name,
            "runtime_model_id": model_id,
            "runtime_model_path": model_path,
            "runtime_source_kind": source_kind,
            "runtime_source_repo": source_repo,
        }

    @staticmethod
    def _runtime_name_is_live(runtime_name: str) -> bool:
        normalized = runtime_name.strip().lower()
        if not normalized:
            return False
        if normalized.startswith("deterministic"):
            return False
        if "unavailable" in normalized:
            return False
        return True

    @staticmethod
    def _validate_required_live_model(runtime_evidence: dict[str, str], *, operation: str) -> None:
        if runtime_evidence.get("runtime_live_model") == "true" and runtime_evidence.get("runtime_model_handle"):
            return
        runtime_name = runtime_evidence.get("runtime_name", "") or "missing"
        model_handle = runtime_evidence.get("runtime_model_handle", "") or "missing"
        raise ValueError(
            f"{operation} requires a loaded live model runtime; "
            f"runtime_name={runtime_name}; model_handle={model_handle}"
        )

    @staticmethod
    def _resolve_int_parameter(
        *,
        explicit_value: int | None,
        parameters: dict[str, str] | None,
        key: str,
    ) -> int:
        if explicit_value is not None:
            return max(int(explicit_value), 0)
        raw_value = (parameters or {}).get(key)
        if raw_value is None or raw_value == "":
            return 0
        try:
            return max(int(raw_value), 0)
        except ValueError:
            return 0

    @staticmethod
    def _requested_parameter(
        *,
        explicit_value: int | None,
        parameters: dict[str, str] | None,
        key: str,
    ) -> str:
        if explicit_value is not None:
            return str(explicit_value)
        raw_value = (parameters or {}).get(key)
        return str(raw_value) if raw_value not in (None, "") else ""

    @staticmethod
    def _resolve_scoring_mode(
        *,
        suite_id: str,
        requested_scoring_mode: str,
        default_scoring_mode: str,
    ) -> str:
        resolved = requested_scoring_mode.strip() or default_scoring_mode
        supported_modes = _SUITE_SUPPORTED_SCORING_MODES.get(suite_id, {default_scoring_mode})
        if resolved not in supported_modes:
            raise ValueError(f"Unsupported scoring_mode '{resolved}' for suite {suite_id}")
        return resolved

    @staticmethod
    def _resolve_code_exec_policy(
        *,
        suite_id: str,
        requested_code_exec_policy: str,
    ) -> str:
        normalized = requested_code_exec_policy.strip()
        if suite_id in _CODE_EVAL_SUITES:
            if normalized in _CODE_EXEC_DISABLED_POLICIES:
                raise ValueError(f"suite {suite_id} requires code_exec_policy to allow execution")
            if normalized and normalized not in _CODE_EXEC_ENABLED_POLICIES:
                raise ValueError(f"Unsupported code_exec_policy '{normalized}' for suite {suite_id}")
            return normalized or "sandboxed"
        if normalized in _CODE_EXEC_ENABLED_POLICIES:
            raise ValueError(
                f"code_exec_policy '{normalized}' is only supported for code evaluation suites"
            )
        if normalized and normalized not in _CODE_EXEC_DISABLED_POLICIES:
            raise ValueError(f"Unsupported code_exec_policy '{normalized}' for suite {suite_id}")
        return normalized or "disabled"

    @staticmethod
    def _dataset_sample_load_limit(*, sample_size: int, few_shot: int, seed: int) -> int | None:
        bounded_sample_size = max(sample_size, 0)
        bounded_few_shot = max(few_shot, 0)
        total_requested = bounded_sample_size + bounded_few_shot
        if total_requested == 0:
            return 0
        if seed <= 0:
            return total_requested
        return None

    @staticmethod
    def _plan_evaluation_samples(
        *,
        samples: list[dict[str, object]],
        sample_size: int,
        few_shot: int,
        seed: int,
    ) -> tuple[tuple[dict[str, object], ...], list[dict[str, object]]]:
        ordered = list(samples) if seed > 0 else samples
        if seed > 0:
            random.Random(seed).shuffle(ordered)
        bounded_sample_size = max(sample_size, 0)
        bounded_few_shot = max(few_shot, 0)
        few_shot_examples = tuple(ordered[:bounded_few_shot])
        selected = ordered[bounded_few_shot : bounded_few_shot + bounded_sample_size]
        return few_shot_examples, selected

    @staticmethod
    def _resolve_float_parameter(
        *,
        parameters: dict[str, str] | None,
        key: str,
        default_value: float,
    ) -> float:
        raw_value = (parameters or {}).get(key)
        if raw_value is None or raw_value == "":
            return float(default_value)
        try:
            return float(raw_value)
        except ValueError:
            return float(default_value)

    @staticmethod
    def _sample_probe_means(samples: Any, field_names: tuple[str, ...]) -> dict[str, float]:
        if not field_names:
            return {}
        totals = {field_name: 0.0 for field_name in field_names}
        sample_count = 0
        for sample in samples:
            sample_count += 1
            for field_name in field_names:
                totals[field_name] += float(getattr(sample, field_name, 0.0) or 0.0)
        if sample_count == 0:
            return {field_name: 0.0 for field_name in field_names}
        return {
            field_name: round(total / sample_count, 4)
            for field_name, total in totals.items()
        }

    @staticmethod
    def _summarize_sample_records(
        samples: Any,
        *,
        threshold: float,
        include_code_exec_metrics: bool,
    ) -> SampleSummary:
        sample_count = 0
        typed_score_total = 0.0
        extraction_success_count = 0
        validation_success_count = 0
        threshold_pass_count = 0
        code_exec_pass_count = 0
        for sample in samples:
            sample_count += 1
            typed_score = float(getattr(sample, "typed_score", 0.0) or 0.0)
            typed_score_total += typed_score
            extraction_status = str(getattr(sample, "extraction_status", "") or "")
            validation_status = str(getattr(sample, "validation_status", "") or "")
            if extraction_status == "extracted":
                extraction_success_count += 1
            if validation_status == "validated":
                validation_success_count += 1
                if typed_score >= threshold:
                    threshold_pass_count += 1
            if include_code_exec_metrics:
                if (
                    str(getattr(sample, "code_test_status", "") or "") == "passed"
                    and str(getattr(sample, "code_runtime_status", "") or "") == "ok"
                ):
                    code_exec_pass_count += 1
        denominator = max(sample_count, 1)
        return SampleSummary(
            sample_count=sample_count,
            typed_score_mean=round(typed_score_total / denominator, 4),
            extraction_success_count=extraction_success_count,
            validation_success_count=validation_success_count,
            threshold_pass_count=threshold_pass_count,
            scored_sample_count=validation_success_count,
            failure_count=sample_count - validation_success_count,
            extraction_success_rate=round(extraction_success_count / denominator, 4),
            validation_success_rate=round(validation_success_count / denominator, 4),
            threshold_pass_rate=round(threshold_pass_count / denominator, 4),
            code_exec_pass_count=(code_exec_pass_count if include_code_exec_metrics else None),
            code_exec_fail_count=(sample_count - code_exec_pass_count if include_code_exec_metrics else None),
        )

    @staticmethod
    def _sample_probe_mean(samples: tuple[EvaluationSample, ...], field_name: str) -> float:
        values = [float(getattr(sample, field_name, 0.0) or 0.0) for sample in samples]
        if not values:
            return 0.0
        return round(sum(values) / len(values), 4)

    @staticmethod
    def _profile_from_manifest(
        manifest: dict[str, object],
        *,
        suite_id: str,
        default_scoring_mode: str,
    ) -> EvaluationProfileDefinition:
        raw_threshold = manifest.get("threshold")
        try:
            threshold = float(raw_threshold or 1.0)
        except (TypeError, ValueError):
            threshold = 1.0
        return EvaluationProfileDefinition(
            profile_type=str(manifest.get("profile_type") or "final_result"),
            result_kind=str(manifest.get("result_kind") or "text"),
            extraction_mode=str(manifest.get("extraction_mode") or "heuristic_final"),
            scoring_mode=str(manifest.get("scoring_mode") or default_scoring_mode),
            threshold=threshold,
            output_schema=(
                dict(manifest["output_schema"])
                if isinstance(manifest.get("output_schema"), dict)
                else None
            ),
            ignored_paths=tuple(
                str(value)
                for value in manifest.get("ignored_paths", [])
                if str(value).strip()
            ),
        )

    @staticmethod
    def _validate_task_kind_against_dataset(
        *,
        dataset_id: str,
        samples: list[dict[str, object]],
        manifest_input_modalities: tuple[str, ...],
        task_kind: str,
    ) -> None:
        if task_kind in _MULTIMODAL_TASK_KINDS:
            return
        if "image" in manifest_input_modalities or any(
            EvaluationCore._sample_declares_image_media(sample)
            for sample in samples
        ):
            raise ValueError(
                f"Evaluation dataset {dataset_id} requires image inputs, but resolved task_kind={task_kind}."
            )

    @staticmethod
    def _validate_live_multimodal_execution(
        *,
        loaded_model,
        manifest_input_modalities: tuple[str, ...],
        samples: list[dict[str, object]],
        task_kind: str,
    ) -> None:
        if task_kind not in _MULTIMODAL_TASK_KINDS or loaded_model is None:
            return
        if "image" not in manifest_input_modalities and not any(
            EvaluationCore._sample_declares_image_media(sample)
            for sample in samples
        ):
            return
        runtime_model = getattr(loaded_model, "runtime_model", {})
        metadata = runtime_model.get("metadata", {}) if isinstance(runtime_model, dict) else {}
        if str(metadata.get("melix.vlm.execution_mode", "")).strip() == "text_backed":
            raise ValueError(
                "The loaded VLM package does not include vision weights, so image evaluation is unavailable."
            )

    def _build_sample_record(
        self,
        *,
        job_id: str,
        suite_id: str,
        dataset_id: str,
        task_kind: str,
        manifest_input_modalities: tuple[str, ...],
        dataset_root: Path,
        few_shot_examples: tuple[dict[str, object], ...],
        index: int,
        sample: dict[str, object],
        profile: EvaluationProfileDefinition,
        loaded_model=None,
        scoring_mode: str,
        code_exec_policy: str,
        seed: int,
        job_parameters: dict[str, str],
        request_label: str = "",
    ) -> EvaluationSample:
        system_text = EvaluationCore._system_text_for_sample(sample)
        input_text = EvaluationCore._input_text_for_sample(sample)
        target = EvaluationCore._target_text_for_sample(sample)
        choices = self._sample_choices(sample)
        media_references = EvaluationCore._media_references_for_sample(
            task_kind=task_kind,
            dataset_root=dataset_root,
            sample=sample,
        )
        input_modalities = EvaluationCore._input_modalities_for_sample(
            task_kind=task_kind,
            prompt=input_text,
            media_references=media_references,
            manifest_input_modalities=manifest_input_modalities,
        )
        started_at = time.perf_counter()
        raw_response = ""
        sample_render_ms = 0.0
        inference_ms = 0.0
        code_language = ""
        code_entry_point = ""
        code_compile_status = ""
        code_runtime_status = ""
        code_timeout_status = ""
        code_test_status = ""
        code_tests_passed = 0
        code_tests_total = 0
        code_failure_detail = ""
        if loaded_model is not None:
            raw_response, sample_render_ms, inference_ms = EvaluationCore._execute_live_prompt(
                registry=self._registry,
                loaded_model=loaded_model,
                messages=EvaluationCore._evaluation_messages(
                    prompt=input_text,
                    expected=target,
                    scoring_mode=scoring_mode,
                    choices=choices,
                    system_text=system_text,
                    result_kind=profile.result_kind,
                    media_references=media_references,
                    few_shot_examples=few_shot_examples,
                    dataset_root=dataset_root,
                    task_kind=task_kind,
                ),
                expected=target,
                result_kind=profile.result_kind,
                request_id=self._request_id(
                    job_id=job_id,
                    suite_id=suite_id,
                    sample_id=str(sample.get("id", index)),
                    request_label=request_label,
                ),
                seed=seed,
            )
        else:
            inference_started_at = time.perf_counter()
            if task_kind in _MULTIMODAL_TASK_KINDS:
                raw_response = ""
            else:
                raw_response = EvaluationCore._deterministic_answer(input_text)
            inference_ms = round((time.perf_counter() - inference_started_at) * 1_000.0, 4)
        duration_s = round(time.perf_counter() - started_at, 6)
        if loaded_model is None and task_kind in _MULTIMODAL_TASK_KINDS:
            return build_evaluation_sample_record(
                job_id=job_id,
                suite_id=suite_id,
                dataset_id=dataset_id,
                sample_id=str(sample.get("id", index)),
                system=system_text,
                input_text=input_text,
                target=target,
                raw_response="",
                extracted_result="",
                typed_score=0.0,
                time_s=duration_s,
                extraction_status="unsupported_multimodal_offline",
                validation_status="not_validated",
                failure_reason="unsupported_multimodal_offline",
                task_kind=task_kind,
                input_modalities=input_modalities,
                media_references=media_references,
                sample_render_ms=sample_render_ms,
                inference_ms=inference_ms,
                raw_response_chars=len(raw_response),
                extracted_result_chars=0,
                failure_stage="inference",
            )
        extracted_result = ""
        extraction_status = ""
        typed_score = 0.0
        validation_status = "not_validated"
        failure_reason = ""
        extraction_ms = 0.0
        validation_ms = 0.0
        scoring_ms = 0.0
        if scoring_mode == "pass_at_1":
            extraction_started_at = time.perf_counter()
            extracted_result, parse_status = extract_candidate_code(raw_response)
            extraction_ms = round((time.perf_counter() - extraction_started_at) * 1_000.0, 4)
            extraction_status = "extracted" if extracted_result.strip() else (parse_status or "empty_prediction")
            failure_reason = "" if extraction_status == "extracted" else parse_status
            if extraction_status == "extracted":
                test_code = self._sample_test_code(sample, job_parameters)
                if not test_code.strip():
                    raise ValueError(
                        f"Code evaluation sample {sample.get('id', index)} is missing test_code"
                    )
                code_entry_point = self._sample_entry_point(sample, job_parameters)
                validation_started_at = time.perf_counter()
                code_result = run_python_code_evaluation(
                    candidate_code=extracted_result,
                    entry_point=code_entry_point,
                    test_code=test_code,
                    timeout_seconds=max(
                        int(self._sample_code_timeout_seconds(sample, job_parameters)),
                        1,
                    ),
                )
                validation_ms = round((time.perf_counter() - validation_started_at) * 1_000.0, 4)
                scoring_ms = validation_ms
                code_language = "python"
                code_compile_status = code_result.compile_status
                code_runtime_status = code_result.runtime_status
                code_timeout_status = code_result.timeout_status
                code_test_status = code_result.test_status
                code_tests_passed = code_result.tests_passed
                code_tests_total = code_result.tests_total
                code_failure_detail = code_result.failure_detail
                validation_status = "validated"
                typed_score = 1.0 if code_result.passed else 0.0
                failure_reason = code_result.failure_detail if not code_result.passed else ""
        elif scoring_mode in {"multiple_choice_accuracy", "exact_match"}:
            extraction_started_at = time.perf_counter()
            extracted_result, parse_status = EvaluationCore._parse_prediction(
                suite_id=suite_id,
                raw_response=raw_response,
                expected=target,
            )
            extraction_ms = round((time.perf_counter() - extraction_started_at) * 1_000.0, 4)
            extraction_status = "extracted" if extracted_result.strip() else (parse_status or "empty_prediction")
            failure_reason = "" if extraction_status == "extracted" else parse_status
            if extraction_status == "extracted":
                validation_status = "validated"
                scoring_started_at = time.perf_counter()
                typed_score = 1.0 if EvaluationCore._score_prediction(
                    sample=sample,
                    expected=target,
                    predicted=extracted_result,
                    scoring_mode=scoring_mode,
                ) else 0.0
                scoring_ms = round((time.perf_counter() - scoring_started_at) * 1_000.0, 4)
                validation_ms = scoring_ms
        else:
            extraction_started_at = time.perf_counter()
            extraction = extract_final_result(
                raw_response=raw_response,
                result_kind=profile.result_kind,
                extraction_mode=profile.extraction_mode,
            )
            extraction_ms = round((time.perf_counter() - extraction_started_at) * 1_000.0, 4)
            extracted_result = extraction.extracted_result
            extraction_status = extraction.extraction_status
            failure_reason = extraction.failure_reason
            if extraction.extraction_status == "extracted":
                scoring_started_at = time.perf_counter()
                scoring = score_final_result(
                    extracted_result=extracted_result,
                    target=target,
                    profile=profile,
                )
                scoring_ms = round((time.perf_counter() - scoring_started_at) * 1_000.0, 4)
                validation_ms = scoring_ms
                typed_score = scoring.typed_score
                validation_status = scoring.validation_status
                failure_reason = scoring.failure_reason
        failure_stage = EvaluationCore._evaluation_failure_stage(
            extraction_status=extraction_status,
            validation_status=validation_status,
            typed_score=typed_score,
            threshold=profile.threshold,
        )
        return build_evaluation_sample_record(
            job_id=job_id,
            suite_id=suite_id,
            dataset_id=dataset_id,
            sample_id=str(sample.get("id", index)),
            system=system_text,
            input_text=input_text,
            target=target,
            raw_response=raw_response,
            extracted_result=extracted_result,
            typed_score=typed_score,
            time_s=duration_s,
            extraction_status=extraction_status,
            validation_status=validation_status,
            failure_reason=failure_reason,
            task_kind=task_kind,
            input_modalities=input_modalities,
            media_references=media_references,
            code_language=code_language,
            code_entry_point=code_entry_point,
            code_compile_status=code_compile_status,
            code_runtime_status=code_runtime_status,
            code_timeout_status=code_timeout_status,
            code_test_status=code_test_status,
            code_tests_passed=code_tests_passed,
            code_tests_total=code_tests_total,
            code_failure_detail=code_failure_detail,
            category_label=EvaluationCore._sample_label(sample, "category"),
            subject_label=EvaluationCore._sample_label(sample, "subject"),
            sample_render_ms=sample_render_ms,
            inference_ms=inference_ms,
            extraction_ms=extraction_ms,
            validation_ms=validation_ms,
            scoring_ms=scoring_ms,
            raw_response_chars=len(raw_response),
            extracted_result_chars=len(extracted_result),
            failure_stage=failure_stage,
        )

    @staticmethod
    def _sample_label(sample: dict[str, object], key_root: str) -> str:
        for key in (f"{key_root}_label", key_root):
            value = str(sample.get(key, "")).strip()
            if value:
                return value
        return ""

    @staticmethod
    def _request_id(
        *,
        job_id: str,
        suite_id: str,
        sample_id: str,
        request_label: str = "",
    ) -> str:
        if request_label:
            return f"eval:{job_id}:{suite_id}:{request_label}:{sample_id}"
        return f"eval:{job_id}:{suite_id}:{sample_id}"

    @staticmethod
    def _evaluation_failure_stage(
        *,
        extraction_status: str,
        validation_status: str,
        typed_score: float,
        threshold: float,
    ) -> str:
        if extraction_status != "extracted":
            return "extraction"
        if validation_status != "validated":
            return "validation"
        if threshold > 0.0 and typed_score < threshold:
            return "scoring"
        return ""

    @staticmethod
    def _deterministic_answer(prompt: str) -> str:
        match = _ARITHMETIC_PROMPT_PATTERN.fullmatch(prompt)
        if match is None:
            return ""

        left = int(match.group(1))
        operator = match.group(2)
        right = int(match.group(3))
        if operator == "+":
            return str(left + right)
        return str(left - right)

    @staticmethod
    def _execute_live_prompt(
        *,
        registry,
        loaded_model,
        messages: list[common_pb2.ChatMessage],
        expected: str,
        result_kind: str = "text",
        request_id: str,
        seed: int,
    ) -> tuple[str, float, float]:
        runtime = registry.runtime_for_loaded_model(loaded_model)
        state = registry.start_request(request_id, runtime_kind=loaded_model.runtime_kind)
        chunks: list[str] = []
        try:
            render_started_at = time.perf_counter()
            rendered_prompt = runtime.render_prompt(
                messages,
                loaded_model=loaded_model.runtime_model,
                execution_ext={},
            )
            sample_render_ms = round((time.perf_counter() - render_started_at) * 1_000.0, 4)
            sampling = common_pb2.SamplingConfig(
                temperature=0.0,
                top_p=1.0,
                top_k=1,
                seed=max(seed, 0),
                max_output_tokens=EvaluationCore._evaluation_max_output_tokens(
                    expected,
                    result_kind=result_kind,
                ),
            )
            inference_started_at = time.perf_counter()
            for runtime_event in runtime.generate_tokens(
                loaded_model.runtime_model,
                rendered_prompt,
                sampling,
                state.cancel_event,
                execution_ext={},
            ):
                text = getattr(runtime_event, "text", "")
                if text:
                    chunks.append(str(text))
            inference_ms = round((time.perf_counter() - inference_started_at) * 1_000.0, 4)
        finally:
            if loaded_model.runtime_kind in {"ocr", "vlm"} and hasattr(runtime, "last_probe_snapshot"):
                registry.record_vision_probe(loaded_model.runtime_kind, runtime.last_probe_snapshot())
            registry.finish_request(request_id)
        return "".join(chunks).strip(), sample_render_ms, inference_ms

    @staticmethod
    def _evaluation_messages(
        prompt: str,
        expected: str,
        scoring_mode: str = "",
        choices: tuple[str, ...] = (),
        system_text: str = "",
        result_kind: str = "text",
        media_references: tuple[str, ...] = (),
        few_shot_examples: tuple[dict[str, object], ...] = (),
        dataset_root: Path | None = None,
        task_kind: str = "text-generation",
    ) -> list[common_pb2.ChatMessage]:
        if scoring_mode == "pass_at_1":
            instruction = "Return only executable Python code for the requested solution. Do not include explanations."
        elif scoring_mode == "multiple_choice_accuracy" and choices:
            instruction = "Return only the single best answer choice letter. Do not include reasoning or explanation."
        elif result_kind == "json":
            instruction = "Return only the final JSON result. Do not include reasoning or explanation."
        elif EvaluationCore._looks_like_numeric(expected):
            instruction = "Return only the final numeric answer. Do not include reasoning or explanation."
        elif EvaluationCore._looks_like_option(expected):
            instruction = "Return only the single best answer choice letter. Do not include reasoning or explanation."
        else:
            instruction = "Return only the final short answer. Do not include reasoning or explanation."
        resolved_system_text = instruction
        if system_text.strip():
            resolved_system_text = f"{instruction}\n\n{system_text.strip()}"
        messages = [
            common_pb2.ChatMessage(role="system", parts=[common_pb2.MessagePart(text=resolved_system_text)]),
        ]
        for demo_sample in few_shot_examples:
            demo_prompt = EvaluationCore._input_text_for_sample(demo_sample)
            demo_media_references = EvaluationCore._media_references_for_sample(
                task_kind=task_kind,
                dataset_root=dataset_root or Path.cwd(),
                sample=demo_sample,
            )
            messages.append(
                common_pb2.ChatMessage(
                    role="user",
                    parts=EvaluationCore._message_parts(
                        prompt=demo_prompt,
                        media_references=demo_media_references,
                    ),
                )
            )
            messages.append(
                common_pb2.ChatMessage(
                    role="assistant",
                    parts=[common_pb2.MessagePart(text=EvaluationCore._target_text_for_sample(demo_sample))],
                )
            )
        messages.append(
            common_pb2.ChatMessage(
                role="user",
                parts=EvaluationCore._message_parts(
                    prompt=prompt,
                    media_references=media_references,
                ),
            )
        )
        return messages

    @staticmethod
    def _message_parts(
        *,
        prompt: str,
        media_references: tuple[str, ...],
    ) -> list[common_pb2.MessagePart]:
        user_parts: list[common_pb2.MessagePart] = []
        if prompt:
            user_parts.append(common_pb2.MessagePart(text=prompt))
        for media_reference in media_references:
            user_parts.append(
                common_pb2.MessagePart(
                    image_uri=media_reference,
                    media=common_pb2.MediaMetadata(
                        media_type=common_pb2.MEDIA_TYPE_IMAGE,
                        source_kind=common_pb2.MEDIA_SOURCE_URI,
                        filename=Path(media_reference).name,
                    ),
                )
            )
        if not user_parts:
            user_parts.append(common_pb2.MessagePart(text=prompt))
        return user_parts

    @staticmethod
    def _sample_prompt(sample: dict[str, object]) -> str:
        return str(sample.get("prompt", sample.get("question", "")))

    @staticmethod
    def _sample_expected(sample: dict[str, object]) -> str:
        return str(sample.get("expected", sample.get("answer", ""))).strip()

    @staticmethod
    def _sample_choices(sample: dict[str, object]) -> tuple[str, ...]:
        raw_choices = sample.get("choices")
        if isinstance(raw_choices, (list, tuple)):
            return tuple(str(choice).strip() for choice in raw_choices if str(choice).strip())
        return ()

    @staticmethod
    def _sample_entry_point(sample: dict[str, object], job_parameters: dict[str, str]) -> str:
        raw_value = sample.get("entry_point", job_parameters.get("entry_point", ""))
        return str(raw_value).strip()

    @staticmethod
    def _sample_test_code(sample: dict[str, object], job_parameters: dict[str, str]) -> str:
        raw_value = sample.get(
            "test_code",
            sample.get("test", job_parameters.get("test_code", job_parameters.get("test", ""))),
        )
        return str(raw_value)

    @staticmethod
    def _sample_code_timeout_seconds(sample: dict[str, object], job_parameters: dict[str, str]) -> float:
        raw_value = sample.get("code_timeout_seconds", job_parameters.get("code_timeout_seconds", "5"))
        try:
            return max(float(raw_value), 0.1)
        except (TypeError, ValueError):
            return 5.0

    @staticmethod
    def _score_prediction(
        *,
        sample: dict[str, object],
        expected: str,
        predicted: str,
        scoring_mode: str,
    ) -> bool:
        if scoring_mode == "multiple_choice_accuracy":
            return EvaluationCore._multiple_choice_match(
                expected=expected,
                predicted=predicted,
                choices=EvaluationCore._sample_choices(sample),
            )
        if scoring_mode == "exact_match":
            return EvaluationCore._answers_match(expected=expected, predicted=predicted)
        raise ValueError(f"Unsupported scoring mode at runtime: {scoring_mode}")

    @staticmethod
    def _multiple_choice_match(
        *,
        expected: str,
        predicted: str,
        choices: tuple[str, ...],
    ) -> bool:
        if EvaluationCore._answers_match(expected=expected, predicted=predicted):
            return True
        if not predicted.strip():
            return False
        resolved_choice = EvaluationCore._resolve_choice_prediction(predicted=predicted, choices=choices)
        if resolved_choice is None:
            return False
        return EvaluationCore._answers_match(expected=expected, predicted=resolved_choice)

    @staticmethod
    def _resolve_choice_prediction(*, predicted: str, choices: tuple[str, ...]) -> str | None:
        if not choices:
            return None
        option = EvaluationCore._extract_option_value(predicted)
        if option is not None:
            option_index = ord(option) - ord("A")
            if 0 <= option_index < len(choices):
                return choices[option_index]
        digit_matches = _DIGIT_TOKEN_PATTERN.findall(predicted)
        if digit_matches:
            choice_index = int(digit_matches[-1]) - 1
            if 0 <= choice_index < len(choices):
                return choices[choice_index]
        normalized_predicted = EvaluationCore._normalized_answer(predicted)
        for choice in choices:
            if EvaluationCore._normalized_answer(choice) == normalized_predicted:
                return choice
        return None

    @staticmethod
    def _media_references_for_sample(
        *,
        task_kind: str,
        dataset_root: Path,
        sample: dict[str, object],
    ) -> tuple[str, ...]:
        if task_kind not in _MULTIMODAL_TASK_KINDS:
            return ()

        references: list[str] = []
        sample_input = sample.get("input")
        input_payload = sample_input if isinstance(sample_input, dict) else {}

        def append_reference(value: object) -> None:
            if isinstance(value, str) and value.strip():
                references.append(
                    EvaluationCore._resolved_media_reference(
                        dataset_root=dataset_root,
                        value=value,
                    )
                )

        append_reference(input_payload.get("image_uri"))
        append_reference(sample.get("image_uri"))
        for key in ("image_uris", "images"):
            raw_value = input_payload.get(key)
            if isinstance(raw_value, (list, tuple)):
                for item in raw_value:
                    append_reference(item)
            raw_value = sample.get(key)
            if isinstance(raw_value, (list, tuple)):
                for item in raw_value:
                    append_reference(item)
        raw_media = input_payload.get("media")
        if isinstance(raw_media, (list, tuple)):
            for item in raw_media:
                if isinstance(item, dict):
                    append_reference(item.get("image_uri"))
                    append_reference(item.get("uri"))
        raw_media = sample.get("media")
        if isinstance(raw_media, (list, tuple)):
            for item in raw_media:
                if isinstance(item, dict):
                    append_reference(item.get("image_uri"))
                    append_reference(item.get("uri"))
        return tuple(dict.fromkeys(references))

    @staticmethod
    def _resolved_media_reference(*, dataset_root: Path, value: str) -> str:
        stripped = value.strip()
        parsed = urlparse(stripped)
        if parsed.scheme in {"http", "https", "file"}:
            return stripped
        candidate = Path(stripped)
        if candidate.is_absolute():
            return str(candidate)
        return str((dataset_root / candidate).resolve())

    @staticmethod
    def _input_modalities_for_sample(
        *,
        task_kind: str,
        prompt: str,
        media_references: tuple[str, ...],
        manifest_input_modalities: tuple[str, ...],
    ) -> tuple[str, ...]:
        modalities: list[str] = []
        if prompt.strip():
            modalities.append("text")
        if media_references or task_kind in _MULTIMODAL_TASK_KINDS:
            modalities.append("image")
        if not modalities:
            modalities.extend(
                modality
                for modality in manifest_input_modalities
                if modality not in modalities
            )
        if not modalities and task_kind == "text-generation":
            modalities.append("text")
        return tuple(modalities)

    @staticmethod
    def _sample_declares_image_media(sample: dict[str, object]) -> bool:
        sample_input = sample.get("input")
        input_payload = sample_input if isinstance(sample_input, dict) else {}
        if isinstance(input_payload.get("image_uri"), str) and str(input_payload.get("image_uri")).strip():
            return True
        for key in ("image_uris", "images"):
            raw_value = input_payload.get(key)
            if isinstance(raw_value, (list, tuple)) and any(str(item).strip() for item in raw_value):
                return True
        raw_media = input_payload.get("media")
        if isinstance(raw_media, (list, tuple)):
            for item in raw_media:
                if not isinstance(item, dict):
                    continue
                if str(item.get("image_uri", "")).strip() or str(item.get("uri", "")).strip():
                    return True
        if isinstance(sample.get("image_uri"), str) and str(sample.get("image_uri")).strip():
            return True
        for key in ("image_uris", "images"):
            raw_value = sample.get(key)
            if isinstance(raw_value, (list, tuple)) and any(str(item).strip() for item in raw_value):
                return True
        raw_media = sample.get("media")
        if isinstance(raw_media, (list, tuple)):
            for item in raw_media:
                if not isinstance(item, dict):
                    continue
                if str(item.get("image_uri", "")).strip() or str(item.get("uri", "")).strip():
                    return True
        return False

    @staticmethod
    def _evaluation_max_output_tokens(expected: str, *, result_kind: str = "text") -> int:
        if result_kind == "json":
            return min(max(256, len(expected.encode("utf-8")) * 2), 2048)
        if EvaluationCore._looks_like_numeric(expected) or EvaluationCore._looks_like_option(expected):
            return 32
        return 128

    @staticmethod
    def _system_text_for_sample(sample: dict[str, object]) -> str:
        return str(sample.get("system", "") or "")

    @staticmethod
    def _input_text_for_sample(sample: dict[str, object]) -> str:
        sample_input = sample.get("input")
        if isinstance(sample_input, dict):
            text = sample_input.get("text")
            if isinstance(text, str):
                return text
        return str(sample.get("prompt", sample.get("question", "")) or "")

    @staticmethod
    def _target_text_for_sample(sample: dict[str, object]) -> str:
        if "target" in sample:
            target_value = sample.get("target")
        else:
            target_value = sample.get("expected", sample.get("answer", ""))
        if isinstance(target_value, str):
            return target_value.strip()
        return json.dumps(target_value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _release_runtime_memory() -> None:
        gc.collect()
        try:
            import mlx.core as mx
        except ModuleNotFoundError:
            return
        try:
            mx.clear_cache()
        except Exception:
            pass
        try:
            if hasattr(mx, "metal"):
                mx.metal.clear_cache()
        except Exception:
            pass

    @staticmethod
    def _parse_prediction(
        *,
        suite_id: str,
        raw_response: str,
        expected: str,
    ) -> tuple[str, str]:
        normalized_response = raw_response.strip()
        if not normalized_response:
            return "", "empty_prediction"

        answer_match = None
        for match in _ANSWER_PREFIX_PATTERN.finditer(normalized_response):
            answer_match = match
        if answer_match is not None:
            candidate = answer_match.group(1).strip()
            parsed = EvaluationCore._parse_candidate_for_expected(candidate=candidate, expected=expected)
            return parsed, "parsed_answer_prefix"

        parsed = EvaluationCore._parse_candidate_for_expected(candidate=normalized_response, expected=expected)
        if parsed != normalized_response:
            if EvaluationCore._looks_like_numeric(expected):
                return parsed, "parsed_numeric"
            if EvaluationCore._looks_like_option(expected):
                return parsed, "parsed_option"
        _ = suite_id
        return parsed, "parsed"

    @staticmethod
    def _parse_candidate_for_expected(*, candidate: str, expected: str) -> str:
        if not candidate:
            return ""
        if EvaluationCore._looks_like_numeric(expected):
            parsed_numeric = EvaluationCore._extract_numeric_value(candidate)
            if parsed_numeric is not None:
                return parsed_numeric
        if EvaluationCore._looks_like_option(expected):
            parsed_option = EvaluationCore._extract_option_value(candidate)
            if parsed_option is not None:
                return parsed_option
        return EvaluationCore._strip_wrapping(candidate)

    @staticmethod
    def _answers_match(*, expected: str, predicted: str) -> bool:
        if not predicted.strip():
            return False
        normalized_expected = EvaluationCore._normalized_answer(expected)
        normalized_predicted = EvaluationCore._normalized_answer(predicted)
        return normalized_expected == normalized_predicted

    @staticmethod
    def _normalized_answer(value: str) -> str:
        stripped = EvaluationCore._strip_wrapping(value)
        numeric = EvaluationCore._extract_numeric_value(stripped)
        if numeric is not None and EvaluationCore._looks_like_numeric(stripped):
            return numeric
        option = EvaluationCore._extract_option_value(stripped)
        if option is not None and EvaluationCore._looks_like_option(stripped):
            return option
        return re.sub(r"\s+", " ", stripped).casefold()

    @staticmethod
    def _strip_wrapping(value: str) -> str:
        return value.strip().strip("`").strip().strip("\"'").strip().rstrip(".")

    @staticmethod
    def _looks_like_numeric(value: str) -> bool:
        return _NUMERIC_TOKEN_PATTERN.fullmatch(value.strip()) is not None

    @staticmethod
    def _extract_numeric_value(value: str) -> str | None:
        result_matches = _NUMERIC_RESULT_PATTERN.findall(value)
        if result_matches:
            numeric = result_matches[-1].lstrip("+")
            if "." in numeric:
                numeric = numeric.rstrip("0").rstrip(".")
            return numeric
        matches = _NUMERIC_TOKEN_PATTERN.findall(value)
        if not matches:
            return None
        numeric = matches[-1].lstrip("+")
        if "." in numeric:
            numeric = numeric.rstrip("0").rstrip(".")
        return numeric

    @staticmethod
    def _looks_like_option(value: str) -> bool:
        normalized = value.strip().upper()
        return len(normalized) == 1 and normalized.isalpha()

    @staticmethod
    def _extract_option_value(value: str) -> str | None:
        matches = _OPTION_TOKEN_PATTERN.findall(value.upper())
        if not matches:
            return None
        return matches[-1].upper()
