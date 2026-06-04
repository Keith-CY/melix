from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import logging
from pathlib import Path
import re
import time
from typing import Any

from packages.protocol.python.worker.v1 import common_pb2
from worker.productization.benchmark_queue import BenchmarkQueueRecord
from worker.productization.evaluation_compare import (
    _DEFAULT_COMPARE_BOOTSTRAP_ITERATIONS,
    _DEFAULT_COMPARE_BOOTSTRAP_SEED,
    _DEFAULT_COMPARE_CONFIDENCE_LEVEL,
    _DEFAULT_COMPARE_EFFECT_THRESHOLD,
    AdapterTargetSpec,
    build_compare_samples,
    load_adapter_target_spec,
    parse_compare_target_adapter_manifest_paths,
    parse_compare_target_model_ids,
    resolve_compare_target_adapters,
    resolve_compare_target_models,
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
    build_evaluation_compare_summary_record,
    build_evaluation_job_record,
    build_evaluation_result_record,
    build_evaluation_sample_record,
)
from worker.productization.statistical_evidence import (
    build_paired_statistical_evidence,
    classify_release_verdict,
)
from worker.productization.topic_membership import (
    SEMANTIC_JUDGE_PROMPT_HASH as TOPIC_SEMANTIC_JUDGE_PROMPT_HASH,
    SEMANTIC_SCORING_MODE as TOPIC_SEMANTIC_SCORING_MODE,
    STRICT_SCORING_MODE as TOPIC_STRICT_SCORING_MODE,
    TOPIC_MEMBERSHIP_PROMPT_ID,
    TOPIC_MEMBERSHIP_SCORING_MODES,
    TOPIC_MEMBERSHIP_SUITE_ID,
    RemoteTopicMembershipTarget,
    TopicMembershipClientResult,
    TopicMembershipPromptSpec,
    evaluate_topic_membership,
    extract_topic_membership_output_json,
    input_payload as topic_membership_input_payload,
    make_topic_membership_client,
    make_topic_membership_semantic_judge_client,
    prompt_snapshot_payload as topic_membership_prompt_snapshot_payload,
    topic_membership_chat_messages,
    topic_prompt_content_hash,
)


_logger = logging.getLogger(__name__)


def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class TopicMembershipRun:
    job: EvaluationJob | EvaluationCompareJob
    results: tuple[EvaluationResult | EvaluationCompareSummary, ...]
    samples: tuple[EvaluationSample | EvaluationCompareSample, ...]
    persisted_paths: dict[str, Path]

    @property
    def result(self) -> EvaluationResult | EvaluationCompareSummary:
        return self.results[0]


def _round_ms(value: float) -> float:
    return round(float(value), 3)


class _LocalTopicMembershipResponseParseError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        raw_response: str,
        request_body_bytes: int,
        response_body_bytes: int,
    ) -> None:
        super().__init__(message)
        self.raw_response = raw_response
        self.request_body_bytes = request_body_bytes
        self.response_body_bytes = response_body_bytes


class _LocalTopicMembershipClient:
    def __init__(
        self,
        *,
        registry,
        loaded_model,
        prompt_spec: TopicMembershipPromptSpec,
        max_output_tokens: int,
        seed: int,
    ) -> None:
        self._registry = registry
        self._loaded_model = loaded_model
        self._prompt_spec = prompt_spec
        self._max_output_tokens = max_output_tokens
        self._seed = seed

    def generate_membership(self, gold_case: dict[str, Any]) -> TopicMembershipClientResult:
        dialogue_id = str(gold_case.get("source_dialogue_id") or "")
        messages = topic_membership_chat_messages(self._prompt_spec, gold_case)
        request_body_bytes = len(
            json.dumps({"messages": messages}, ensure_ascii=False, sort_keys=True).encode("utf-8")
        )
        chat_messages = [
            common_pb2.ChatMessage(
                role=str(message.get("role") or "user"),
                parts=[common_pb2.MessagePart(text=str(message.get("content") or ""))],
            )
            for message in messages
        ]
        request_id = f"topic-membership:local:{dialogue_id or 'sample'}:{time.time_ns()}"
        runtime = self._registry.runtime_for_loaded_model(self._loaded_model)
        state = self._registry.start_request(
            request_id,
            runtime_kind=str(getattr(self._loaded_model, "runtime_kind", "") or "text"),
        )
        chunks: list[str] = []
        try:
            rendered_prompt = runtime.render_prompt(
                chat_messages,
                loaded_model=self._loaded_model.runtime_model,
                template_kwargs={"enable_thinking": False},
                execution_ext={},
            )
            sampling = common_pb2.SamplingConfig(
                temperature=0.0,
                top_p=1.0,
                top_k=1,
                seed=max(self._seed, 0),
                max_output_tokens=self._max_output_tokens,
            )
            for runtime_event in runtime.generate_tokens(
                self._loaded_model.runtime_model,
                rendered_prompt,
                sampling,
                state.cancel_event,
                execution_ext={},
            ):
                text = getattr(runtime_event, "text", "")
                if text:
                    chunks.append(str(text))
        finally:
            runtime_kind = str(getattr(self._loaded_model, "runtime_kind", "") or "")
            if runtime_kind in {"ocr", "vlm"} and hasattr(runtime, "last_probe_snapshot"):
                self._registry.record_vision_probe(runtime_kind, runtime.last_probe_snapshot())
            self._registry.finish_request(request_id)
        raw_response = "".join(chunks).strip()
        response_body_bytes = len(raw_response.encode("utf-8"))
        try:
            output_json = extract_topic_membership_output_json(raw_response)
        except Exception as exc:  # noqa: BLE001
            raise _LocalTopicMembershipResponseParseError(
                str(exc),
                raw_response=raw_response,
                request_body_bytes=request_body_bytes,
                response_body_bytes=response_body_bytes,
            ) from exc
        return TopicMembershipClientResult(
            output_json=output_json,
            raw_response=raw_response,
            request_body_bytes=request_body_bytes,
            response_body_bytes=response_body_bytes,
        )



def run_topic_membership_entrypoint(
    *,
    core: Any,
    model_id: str,
    model_handle: str | None,
    suite_id: str,
    sample_size: int,
    scoring_mode: str | None,
    parameters: dict[str, str],
    remote_target: Any | None,
) -> TopicMembershipRun:
    requested_scoring_mode = scoring_mode or parameters.get("scoring_mode", "")
    loaded_model = core._loaded_model_for_execution(model_handle)
    resolved_scoring_mode = requested_scoring_mode or TOPIC_STRICT_SCORING_MODE
    resolved_suite_id = suite_id or TOPIC_MEMBERSHIP_SUITE_ID
    runner = TopicMembershipEvaluationRunner(core)
    if str(parameters.get("compare_mode", "")).strip():
        return runner._run_topic_membership_compare_suite(
            model_id=model_id,
            suite_id=resolved_suite_id,
            dataset_id=parameters.get("dataset_id", ""),
            sample_size=sample_size,
            scoring_mode=resolved_scoring_mode,
            parameters=dict(parameters),
            loaded_model=loaded_model,
        )
    return runner._run_topic_membership_suite(
        model_id=model_id,
        suite_id=resolved_suite_id,
        dataset_id=parameters.get("dataset_id", ""),
        sample_size=sample_size,
        scoring_mode=resolved_scoring_mode,
        parameters=dict(parameters),
        remote_target=remote_target,
        loaded_model=loaded_model,
    )


class TopicMembershipEvaluationRunner:
    def __init__(self, core: Any) -> None:
        self._core = core

    def __getattr__(self, name: str) -> Any:
        return getattr(self._core, name)

    def _run_topic_membership_suite(
        self,
        *,
        model_id: str,
        suite_id: str,
        dataset_id: str,
        sample_size: int,
        scoring_mode: str,
        parameters: dict[str, str],
        remote_target: Any | None,
        loaded_model: Any | None = None,
    ) -> TopicMembershipRun:
        source_jsonl = parameters.get("topic_membership_source_jsonl") or parameters.get(
            "evaluation_source_locator",
            "",
        )
        if not source_jsonl:
            raise ValueError("topic_membership scoring requires a local JSONL source.")
        resolved_scoring_mode = scoring_mode or TOPIC_STRICT_SCORING_MODE
        if resolved_scoring_mode not in TOPIC_MEMBERSHIP_SCORING_MODES:
            raise ValueError(f"unsupported topic membership scoring mode: {resolved_scoring_mode}")
        uses_remote_target = remote_target is not None and bool(getattr(remote_target, "api_key", ""))
        if not uses_remote_target and (loaded_model is None or self._registry is None):
            raise ValueError("topic_membership scoring requires a remote provider target or a loaded local model.")

        semantic_judge_target = self._semantic_judge_target(parameters)
        if resolved_scoring_mode == TOPIC_SEMANTIC_SCORING_MODE and semantic_judge_target is None:
            raise ValueError("topic_membership_semantic_micro_f1 requires a semantic judge remote target.")

        created_at_unix_ms = int(time.time() * 1000)
        job_id = self._next_job_id()
        output_root = (
            self._jobs_root / "topic-membership" / job_id
            if self._jobs_root is not None
            else Path.cwd() / "topic-membership" / job_id
        )
        resolved_model_id = (
            str(getattr(getattr(loaded_model, "spec", None), "model_id", "") or "")
            if loaded_model is not None
            else ""
        ) or str(getattr(remote_target, "model_id", "") or model_id)
        safe_model_name = re.sub(r"[^A-Za-z0-9._-]+", "_", resolved_model_id).strip("_") or "topic-model"
        predictions_dir = output_root / "predictions"
        reports_dir = output_root / "reports" / safe_model_name
        raw_response_dir = output_root / "raw-responses" / safe_model_name
        predictions_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)
        raw_response_dir.mkdir(parents=True, exist_ok=True)
        prediction_path = predictions_dir / f"{safe_model_name}.jsonl"
        failure_path = predictions_dir / f"{safe_model_name}.failures.jsonl"
        gold_subset_path = output_root / "gold_subset.jsonl"
        summary_path = reports_dir / "topic_membership_summary.json"
        details_path = reports_dir / "topic_membership_details.jsonl"
        trace_path = reports_dir / "topic_membership_dialogue_traces.jsonl"
        row_audit_path = reports_dir / "topic_membership_row_audit.jsonl"
        judge_audit_path = reports_dir / "topic_membership_judge_audit.jsonl"
        prompt_snapshot_path = output_root / "prompt_snapshot.json"

        rows = self._read_topic_membership_rows(Path(source_jsonl), sample_size=sample_size)
        self._write_jsonl_rows(gold_subset_path, rows)
        prompt_spec = self._topic_membership_prompt_spec(parameters)
        prompt_snapshot = topic_membership_prompt_snapshot_payload(prompt_spec)
        prompt_snapshot_path.write_text(
            json.dumps(prompt_snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        runtime_evidence = self._core._runtime_evidence_for_loaded_model(loaded_model)
        if self._core._truthy_parameter(parameters, "require_live_model"):
            self._core._validate_required_live_model(runtime_evidence, operation="topic membership evaluation")
        if uses_remote_target:
            client = make_topic_membership_client(
                RemoteTopicMembershipTarget(
                    provider_kind=str(getattr(remote_target, "provider_kind", "")),
                    base_url=str(getattr(remote_target, "base_url", "")),
                    api_key=str(getattr(remote_target, "api_key", "")),
                    model_id=resolved_model_id,
                    timeout_seconds=int(getattr(remote_target, "timeout_seconds", 0) or 60),
                    extra_body=self._remote_provider_extra_body(parameters),
                ),
                prompt_spec,
            )
            rate_limit_per_minute = int(getattr(remote_target, "rate_limit_per_minute", 0) or 0)
        else:
            client = _LocalTopicMembershipClient(
                registry=self._registry,
                loaded_model=loaded_model,
                prompt_spec=prompt_spec,
                max_output_tokens=int(parameters.get("topic_membership_max_output_tokens") or 4096),
                seed=int(parameters.get("seed") or 0),
            )
            rate_limit_per_minute = 0

        min_interval_seconds = 60.0 / rate_limit_per_minute if rate_limit_per_minute > 0 else 0.0
        last_request_started = 0.0
        prediction_rows: list[dict[str, object]] = []
        failures: list[dict[str, object]] = []
        dialogue_traces: list[dict[str, object]] = []
        started_at = time.perf_counter()

        for line_number, row in enumerate(rows, start=1):
            row_started_at = time.perf_counter()
            dialogue_id = str(row.get("source_dialogue_id") or "")
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
            raw_response = ""
            raw_response_path: Path | None = None
            try:
                client_result = client.generate_membership(row)
                request_duration_ms = self._round_ms((time.perf_counter() - request_started_at) * 1_000.0)
                output_json, raw_response = client_result
                raw_response_path = raw_response_dir / f"{line_number:04d}-{self._safe_path_component(dialogue_id)}.txt"
                raw_response_path.write_text(raw_response, encoding="utf-8")
                prediction_rows.append(
                    {
                        "source_dialogue_id": dialogue_id,
                        "custom_id": dialogue_id,
                        "status": "ok",
                        "model": resolved_model_id,
                        "prompt_sha256": prompt_spec.content_hash.removeprefix("sha256:"),
                        "elapsed_seconds": round((time.perf_counter() - row_started_at), 6),
                        "raw_text": raw_response,
                        "output_json": output_json,
                    }
                )
                dialogue_traces.append(
                    self._topic_membership_dialogue_trace(
                        dialogue_id=dialogue_id,
                        line_number=line_number,
                        status="ok",
                        row_started_at=row_started_at,
                        throttle_sleep_ms=throttle_sleep_ms,
                        request_duration_ms=request_duration_ms,
                        messages=row.get("messages") if isinstance(row.get("messages"), list) else [],
                        request_body_bytes=self._client_result_int(client_result, "request_body_bytes"),
                        response_body_bytes=self._client_result_int(client_result, "response_body_bytes"),
                        raw_response=raw_response,
                        raw_response_path=raw_response_path,
                        predicted_topic_count=self._topic_count_from_output(output_json),
                        error_code=None,
                        failure_reason=None,
                        provider_usage=self._client_result_provider_usage(client_result),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                request_duration_ms = self._round_ms((time.perf_counter() - request_started_at) * 1_000.0)
                raw_response = str(getattr(exc, "raw_response", "") or "")
                if raw_response:
                    raw_response_path = raw_response_dir / f"{line_number:04d}-{self._safe_path_component(dialogue_id)}.txt"
                    raw_response_path.write_text(raw_response, encoding="utf-8")
                status = "parse_error" if isinstance(exc, _LocalTopicMembershipResponseParseError) else "error"
                provider_error_code = self._event_extraction_provider_error_code(exc)
                prediction_row = {
                    "source_dialogue_id": dialogue_id,
                    "custom_id": dialogue_id,
                    "status": status,
                    "model": resolved_model_id,
                    "prompt_sha256": prompt_spec.content_hash.removeprefix("sha256:"),
                    "elapsed_seconds": round((time.perf_counter() - row_started_at), 6),
                    "raw_text": raw_response,
                    "error": str(exc),
                }
                prediction_rows.append(prediction_row)
                failure_record = {
                    "source_dialogue_id": dialogue_id,
                    "line_number": line_number,
                    "reason": str(exc),
                }
                if provider_error_code:
                    failure_record["code"] = provider_error_code
                if raw_response_path is not None:
                    failure_record["raw_response_path"] = str(raw_response_path)
                failures.append(failure_record)
                dialogue_traces.append(
                    self._topic_membership_dialogue_trace(
                        dialogue_id=dialogue_id,
                        line_number=line_number,
                        status=status,
                        row_started_at=row_started_at,
                        throttle_sleep_ms=throttle_sleep_ms,
                        request_duration_ms=request_duration_ms,
                        messages=row.get("messages") if isinstance(row.get("messages"), list) else [],
                        request_body_bytes=self._client_result_int(exc, "request_body_bytes"),
                        response_body_bytes=self._client_result_int(exc, "response_body_bytes"),
                        raw_response=raw_response,
                        raw_response_path=raw_response_path,
                        predicted_topic_count=0,
                        error_code=provider_error_code or status,
                        failure_reason=str(exc),
                        provider_usage={},
                    )
                )

        self._write_jsonl_rows(trace_path, dialogue_traces)
        self._write_jsonl_rows(prediction_path, prediction_rows)
        self._write_jsonl_rows(failure_path, failures)

        judge = None
        if resolved_scoring_mode == TOPIC_SEMANTIC_SCORING_MODE and semantic_judge_target is not None:
            judge = make_topic_membership_semantic_judge_client(semantic_judge_target)
        summary = evaluate_topic_membership(
            gold_jsonl=gold_subset_path,
            pred_jsonl=prediction_path,
            summary_output=summary_path,
            details_output=details_path,
            row_audit_output=row_audit_path,
            judge_audit_output=judge_audit_path if resolved_scoring_mode == TOPIC_SEMANTIC_SCORING_MODE else None,
            scoring_mode=resolved_scoring_mode,
            judge=judge,
            judge_remote_server_id=str(parameters.get("semantic_judge_remote_server_id") or "").strip(),
            judge_model_id=str(getattr(semantic_judge_target, "model_id", "") or ""),
        )
        summary["dialogue_diagnostics"] = self._topic_membership_dialogue_diagnostics(dialogue_traces)
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        duration_seconds = round(time.perf_counter() - started_at, 6)

        strict_membership = summary.get("strict_membership", {})
        if not isinstance(strict_membership, dict):
            strict_membership = {}
        semantic_membership = summary.get("semantic_membership", {})
        if not isinstance(semantic_membership, dict):
            semantic_membership = {}
        primary_score_name = (
            "semantic_membership_f1"
            if resolved_scoring_mode == TOPIC_SEMANTIC_SCORING_MODE
            else "strict_membership_f1"
        )
        primary_score_value = float(
            semantic_membership.get("f1", 0.0)
            if resolved_scoring_mode == TOPIC_SEMANTIC_SCORING_MODE
            else strict_membership.get("f1", 0.0)
        )
        cases = int(summary.get("cases", len(rows)) or len(rows))
        extraction_success_count = sum(1 for row in prediction_rows if row.get("status") == "ok")

        job_parameters = dict(parameters)
        job_parameters.pop("api_key", None)
        job_parameters.pop("remote_api_key", None)
        job_parameters.pop("eval_prompt_system_prompt", None)
        job_parameters.pop("semantic_judge_api_key", None)
        job_parameters.pop("semantic_judge_base_url", None)
        job_parameters.pop("evaluation_hints_text", None)
        resolved_dataset_id = dataset_id or parameters.get("dataset_id") or "topic-membership"
        job_parameters["dataset_root"] = str(Path(source_jsonl).resolve())
        job_parameters["topic_membership_source_jsonl"] = str(Path(source_jsonl).resolve())
        job_parameters["source_sha256"] = _sha256_file(Path(source_jsonl))
        job_parameters["prediction_jsonl"] = str(prediction_path)
        job_parameters["failure_jsonl"] = str(failure_path)
        job_parameters["topic_membership_summary"] = str(summary_path)
        job_parameters["topic_membership_details"] = str(details_path)
        job_parameters["topic_membership_dialogue_traces"] = str(trace_path)
        job_parameters["topic_membership_row_audit"] = str(row_audit_path)
        if resolved_scoring_mode == TOPIC_SEMANTIC_SCORING_MODE:
            job_parameters["topic_membership_judge_audit"] = str(judge_audit_path)
            job_parameters["semantic_judge_remote_server_id"] = str(
                parameters.get("semantic_judge_remote_server_id") or ""
            ).strip()
            job_parameters["semantic_judge_model_id"] = str(getattr(semantic_judge_target, "model_id", "") or "")
            job_parameters["semantic_judge_prompt_hash"] = TOPIC_SEMANTIC_JUDGE_PROMPT_HASH
        job_parameters["prompt_snapshot"] = str(prompt_snapshot_path)
        job_parameters["prompt_id"] = prompt_spec.prompt_id
        job_parameters["prompt_revision_id"] = prompt_spec.revision_id
        job_parameters["prompt_content_hash"] = prompt_spec.content_hash
        job_parameters["effective_scoring_mode"] = resolved_scoring_mode
        job_parameters["scoring_mode"] = resolved_scoring_mode
        job_parameters["contamination_policy"] = "heldout_clean_track"
        job_parameters["clean_track"] = "true"
        job_parameters["training_use_forbidden"] = "true"
        job_parameters.update(runtime_evidence)
        job_parameters.setdefault("remote_model_id", resolved_model_id)

        result_metrics, result_units = self._topic_membership_result_metrics(
            suite_id=suite_id,
            summary=summary,
            duration_seconds=duration_seconds,
        )
        result_metrics[f"eval.{suite_id}.duration_seconds"] = duration_seconds
        result_units[f"eval.{suite_id}.duration_seconds"] = "s"

        job = build_evaluation_job_record(
            job_id=job_id,
            model_id=resolved_model_id,
            task_kind="text-generation",
            source_repo=job_parameters.get("source_repo", ""),
            suite_id=suite_id,
            dataset_id=resolved_dataset_id,
            sample_size=len(rows),
            scoring_mode=resolved_scoring_mode,
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
            primary_score_name=primary_score_name,
            primary_score_value=primary_score_value,
            extraction_success_count=extraction_success_count,
            validation_success_count=extraction_success_count,
            scored_sample_count=cases,
            failure_count=max(cases - extraction_success_count, 0),
            duration_seconds=duration_seconds,
            metrics=result_metrics,
            report_path=str(summary_path),
            units=result_units,
        )
        sample_records = self._topic_membership_sample_records(
            job_id=job.job_id,
            suite_id=suite_id,
            dataset_id=resolved_dataset_id,
            rows=rows,
            prediction_rows=prediction_rows,
            dialogue_traces=dialogue_traces,
            details_path=details_path,
            prompt_spec=prompt_spec,
            scoring_mode=resolved_scoring_mode,
        )
        persisted_paths: dict[str, Path] = {}
        if self._jobs_root is not None:
            queue_root = self._jobs_root / "queue"
            self._queue_store.enqueue(
                queue_root=queue_root,
                record=BenchmarkQueueRecord(
                    queue_item_id=job.job_id,
                    job_kind="evaluation",
                    model_id=resolved_model_id,
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
                samples=sample_records,
                model_memory_summary=self._model_memory_summary(loaded_model=loaded_model),
            )
            self._queue_store.transition(
                queue_root=queue_root,
                queue_item_id=job.job_id,
                status="completed",
                updated_at_unix_ms=int(time.time() * 1000),
            )
        return TopicMembershipRun(job=job, results=(result,), samples=sample_records, persisted_paths=persisted_paths)

    def _run_topic_membership_compare_suite(
        self,
        *,
        model_id: str,
        suite_id: str,
        dataset_id: str,
        sample_size: int,
        scoring_mode: str,
        parameters: dict[str, str],
        loaded_model: Any | None = None,
    ) -> TopicMembershipRun:
        if loaded_model is None or self._registry is None:
            raise ValueError("topic membership compare requires a loaded local base model.")
        target_model_ids = parse_compare_target_model_ids(parameters)
        adapter_manifest_paths = parse_compare_target_adapter_manifest_paths(parameters)
        if not target_model_ids and not adapter_manifest_paths:
            raise ValueError(
                "evaluation compare requires at least one target - pass "
                "compare_target_model_ids and/or compare_target_adapter_manifest_paths."
            )

        created_at_unix_ms = int(time.time() * 1000)
        job_id = self._next_job_id()
        run_root = self._run_root(job_id)
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
        compare_parameters = dict(parameters)
        single_run_parameters = {
            key: value
            for key, value in parameters.items()
            if key
            not in {
                "compare_mode",
                "compare_target_model_ids",
                "compare_target_adapter_manifest_paths",
            }
        }
        try:
            base_run = self._run_topic_membership_suite(
                model_id=model_id,
                suite_id=suite_id,
                dataset_id=dataset_id,
                sample_size=sample_size,
                scoring_mode=scoring_mode,
                parameters=single_run_parameters,
                remote_target=None,
                loaded_model=loaded_model,
            )
            resolved_model_id = str(getattr(base_run.job, "model_id", "") or model_id)
            target_models: dict[str, Any] = {**registered_targets, **ephemeral_targets}
            combined_target_ids: tuple[str, ...] = (
                tuple(tid for tid in target_model_ids if tid in registered_targets)
                + tuple(spec.ephemeral_derived_model_id for spec in adapter_target_specs)
            )
            compare_samples: list[EvaluationCompareSample] = []
            compare_summaries: list[EvaluationCompareSummary] = []
            threshold = self._resolve_float_parameter(
                parameters=parameters,
                key="threshold",
                default_value=0.5,
            )
            report_path = run_root / "evaluation-compare-report.md"
            compare_dataset_id = str(getattr(base_run.job, "dataset_id", "") or dataset_id or "topic-membership")
            for target_model_id in combined_target_ids:
                started_at = time.perf_counter()
                target_run = self._run_topic_membership_suite(
                    model_id=target_model_id,
                    suite_id=suite_id,
                    dataset_id=dataset_id,
                    sample_size=sample_size,
                    scoring_mode=scoring_mode,
                    parameters=single_run_parameters,
                    remote_target=None,
                    loaded_model=target_models[target_model_id],
                )
                target_compare_samples = build_compare_samples(
                    job_id=job_id,
                    suite_id=suite_id,
                    dataset_id=compare_dataset_id,
                    target_model_id=target_model_id,
                    threshold=threshold,
                    base_samples=base_run.samples,
                    target_samples=target_run.samples,
                )
                compare_samples.extend(target_compare_samples)
                compare_summaries.append(
                    self._topic_membership_compare_summary(
                        job_id=job_id,
                        base_model_id=resolved_model_id,
                        target_model_id=target_model_id,
                        suite_id=suite_id,
                        dataset_id=compare_dataset_id,
                        sample_size=len(base_run.samples),
                        scoring_mode=scoring_mode,
                        base_run=base_run,
                        target_run=target_run,
                        compare_samples=target_compare_samples,
                        effect_threshold=self._resolve_float_parameter(
                            parameters=parameters,
                            key="effect_threshold",
                            default_value=_DEFAULT_COMPARE_EFFECT_THRESHOLD,
                        ),
                        confidence_level=self._resolve_float_parameter(
                            parameters=parameters,
                            key="confidence_level",
                            default_value=_DEFAULT_COMPARE_CONFIDENCE_LEVEL,
                        ),
                        bootstrap_iterations=self._resolve_int_parameter(
                            explicit_value=None,
                            parameters=parameters,
                            key="bootstrap_iterations",
                        )
                        or _DEFAULT_COMPARE_BOOTSTRAP_ITERATIONS,
                        bootstrap_seed=self._resolve_int_parameter(
                            explicit_value=None,
                            parameters=parameters,
                            key="bootstrap_seed",
                        )
                        or _DEFAULT_COMPARE_BOOTSTRAP_SEED,
                        duration_seconds=round(time.perf_counter() - started_at, 6),
                        report_path=str(report_path),
                    )
                )

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
            compare_parameters.setdefault("sample_size", str(len(base_run.samples)))
            base_job_parameters = getattr(base_run.job, "parameters", {})
            if isinstance(base_job_parameters, dict):
                for key in (
                    "dataset_root",
                    "source_kind",
                    "source_path",
                    "source_dataset_path",
                    "source_dataset_name",
                    "source_dataset_revision",
                    "source_split",
                    "few_shot",
                    "seed",
                    "scoring_mode",
                    "topic_membership_source_jsonl",
                ):
                    if base_job_parameters.get(key) not in (None, ""):
                        compare_parameters.setdefault(key, str(base_job_parameters[key]))
            compare_job = build_evaluation_compare_job_record(
                job_id=job_id,
                base_model_id=resolved_model_id,
                target_model_ids=combined_target_ids,
                dataset_lineage=self._compare_dataset_lineage(
                    dataset_id=compare_dataset_id,
                    suite_id=suite_id,
                    dataset_root=Path(str(compare_parameters.get("dataset_root", "."))).resolve(),
                    parameters=compare_parameters,
                    sample_size=len(base_run.samples),
                    seed=self._int_parameter_from_mapping(compare_parameters, "seed"),
                    few_shot=self._int_parameter_from_mapping(compare_parameters, "few_shot"),
                    scoring_mode=scoring_mode,
                ),
                target_lineage=tuple(target_lineage_entries),
                task_kind=str(getattr(base_run.job, "task_kind", "text-generation") or "text-generation"),
                source_repo=str(getattr(base_run.job, "source_repo", "") or ""),
                suite_id=suite_id,
                dataset_id=compare_dataset_id,
                sample_size=len(base_run.samples),
                scoring_mode=scoring_mode,
                parameters=compare_parameters,
                status="completed",
                output_dir=str(run_root),
                created_at_unix_ms=created_at_unix_ms,
                updated_at_unix_ms=created_at_unix_ms,
            )
            persisted_paths: dict[str, Path] = {}
            if self._jobs_root is not None:
                queue_root = self._jobs_root / "queue"
                self._queue_store.enqueue(
                    queue_root=queue_root,
                    record=BenchmarkQueueRecord(
                        queue_item_id=compare_job.job_id,
                        job_kind="evaluation",
                        model_id=model_id,
                        suite_ids=(suite_id,),
                        parameters=compare_parameters,
                        status="queued",
                        created_at_unix_ms=created_at_unix_ms,
                        updated_at_unix_ms=created_at_unix_ms,
                    ),
                )
                self._queue_store.transition(
                    queue_root=queue_root,
                    queue_item_id=compare_job.job_id,
                    status="running",
                    updated_at_unix_ms=created_at_unix_ms + 1,
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
            return TopicMembershipRun(
                job=compare_job,
                results=tuple(compare_summaries),
                samples=tuple(compare_samples),
                persisted_paths=persisted_paths,
            )
        finally:
            for handle in ephemeral_unload_handles:
                try:
                    self._registry.unload_model(handle)
                except Exception as unload_exc:  # noqa: BLE001
                    _logger.warning(
                        "Failed to unload ephemeral adapter compare target "
                        "(handle=%s): %s",
                        handle,
                        unload_exc,
                    )

    def _topic_membership_sample_records(
        self,
        *,
        job_id: str,
        suite_id: str,
        dataset_id: str,
        rows: list[dict[str, object]],
        prediction_rows: list[dict[str, object]],
        dialogue_traces: list[dict[str, object]],
        details_path: Path,
        prompt_spec: TopicMembershipPromptSpec,
        scoring_mode: str,
    ) -> tuple[EvaluationSample, ...]:
        predictions_by_dialogue = {
            str(row.get("source_dialogue_id") or ""): row
            for row in prediction_rows
            if isinstance(row, dict)
        }
        traces_by_dialogue = {
            str(trace.get("source_dialogue_id") or ""): trace
            for trace in dialogue_traces
            if isinstance(trace, dict)
        }
        scores_by_dialogue = TopicMembershipEvaluationRunner._topic_membership_dialogue_scores(
            details_path,
            scoring_mode=scoring_mode,
        )
        sample_records: list[EvaluationSample] = []
        for index, row in enumerate(rows, start=1):
            dialogue_id = str(row.get("source_dialogue_id") or index)
            prediction = predictions_by_dialogue.get(dialogue_id, {})
            output_json = prediction.get("output_json") if isinstance(prediction, dict) else None
            if not isinstance(output_json, dict):
                output_json = {}
            trace = traces_by_dialogue.get(dialogue_id, {})
            trace_status = str(trace.get("status") or "failed") if isinstance(trace, dict) else "failed"
            raw_response = self._core._event_extraction_raw_response_from_trace(trace)
            failure_reason = str(trace.get("failure_reason") or "") if isinstance(trace, dict) else ""
            duration_ms = float(trace.get("total_duration_ms", 0.0) or 0.0) if isinstance(trace, dict) else 0.0
            validation_status = "validated" if trace_status == "ok" else "not_validated"
            extraction_status = "extracted" if trace_status == "ok" else trace_status
            extracted_result = json.dumps(output_json, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            target = json.dumps(
                {
                    "gold_topics": row.get("gold_topics", []),
                    "expected_topic_count_range": row.get("expected_topic_count_range", []),
                    "allowed_fallback_reasons": row.get("allowed_fallback_reasons", []),
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            sample_records.append(
                build_evaluation_sample_record(
                    job_id=job_id,
                    suite_id=suite_id,
                    dataset_id=dataset_id,
                    sample_id=dialogue_id,
                    system=prompt_spec.system_prompt,
                    input_text=json.dumps(
                        topic_membership_input_payload(row),
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    target=target,
                    raw_response=raw_response,
                    extracted_result=extracted_result,
                    typed_score=float(scores_by_dialogue.get(dialogue_id, 0.0)),
                    time_s=round(duration_ms / 1_000.0, 6),
                    extraction_status=extraction_status,
                    validation_status=validation_status,
                    failure_reason=failure_reason,
                    task_kind="text-generation",
                    input_modalities=("text",),
                    raw_response_chars=len(raw_response),
                    extracted_result_chars=len(extracted_result),
                    failure_stage="" if trace_status == "ok" else "extraction",
                    parse_status=trace_status,
                )
            )
        return tuple(sample_records)

    @staticmethod
    def _topic_membership_dialogue_scores(details_path: Path, *, scoring_mode: str) -> dict[str, float]:
        score_field = "semantic_membership" if scoring_mode == TOPIC_SEMANTIC_SCORING_MODE else "strict_membership"
        scores: dict[str, float] = {}
        if not details_path.is_file():
            return scores
        with details_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                dialogue_id = str(row.get("source_dialogue_id") or "").strip()
                metrics = row.get(score_field)
                if dialogue_id and isinstance(metrics, dict):
                    scores[dialogue_id] = round(float(metrics.get("f1", 0.0) or 0.0), 4)
        return scores

    @staticmethod
    def _topic_membership_dialogue_trace(
        *,
        dialogue_id: str,
        line_number: int,
        status: str,
        row_started_at: float,
        throttle_sleep_ms: float,
        request_duration_ms: float,
        messages: list[object],
        request_body_bytes: int,
        response_body_bytes: int,
        raw_response: str,
        raw_response_path: Path | None,
        predicted_topic_count: int,
        error_code: str | None,
        failure_reason: str | None,
        provider_usage: dict[str, int],
    ) -> dict[str, object]:
        text_chars = 0
        for message in messages:
            if isinstance(message, dict):
                text_chars += len(str(message.get("text") or ""))
        return {
            "source_dialogue_id": dialogue_id,
            "dialogue_id": dialogue_id,
            "line_number": line_number,
            "status": status,
            "total_duration_ms": _round_ms((time.perf_counter() - row_started_at) * 1_000.0),
            "request_duration_ms": request_duration_ms,
            "throttle_sleep_ms": throttle_sleep_ms,
            "message_count": len(messages),
            "message_text_char_count": text_chars,
            "request_body_bytes": request_body_bytes,
            "response_body_bytes": response_body_bytes,
            "raw_response_chars": len(raw_response),
            "raw_response_path": str(raw_response_path) if raw_response_path is not None else None,
            "predicted_topic_count": predicted_topic_count,
            "error_code": error_code,
            "failure_reason": failure_reason,
            "provider_usage": provider_usage,
        }

    def _topic_membership_dialogue_diagnostics(self, traces: list[dict[str, object]]) -> dict[str, object]:
        status_counts: dict[str, int] = {}
        for trace in traces:
            status = str(trace.get("status") or "")
            if status:
                status_counts[status] = status_counts.get(status, 0) + 1
        return {
            "dialogue_status_counts": status_counts,
            "request_duration_ms": self._core._latency_stats(self._core._numeric_trace_values(traces, "request_duration_ms")),
            "total_duration_ms": self._core._latency_stats(self._core._numeric_trace_values(traces, "total_duration_ms")),
            "total_throttle_sleep_ms": _round_ms(self._core._numeric_trace_sum(traces, "throttle_sleep_ms")),
        }

    @staticmethod
    def _topic_membership_result_metrics(
        *,
        suite_id: str,
        summary: dict[str, object],
        duration_seconds: float,
    ) -> tuple[dict[str, float], dict[str, str]]:
        metrics: dict[str, float] = {
            f"eval.{suite_id}.cases": float(summary.get("cases", 0.0) or 0.0),
            f"eval.{suite_id}.missing_predictions": float(summary.get("missing_predictions", 0.0) or 0.0),
            f"eval.{suite_id}.json_valid_rate": float(summary.get("json_valid_rate", 0.0) or 0.0),
            f"eval.{suite_id}.topic_count_range_accuracy": float(
                summary.get("topic_count_range_accuracy", 0.0) or 0.0
            ),
            f"eval.{suite_id}.fallback_accuracy": float(summary.get("fallback_accuracy", 0.0) or 0.0),
            f"eval.{suite_id}.duration_seconds": float(duration_seconds),
        }
        units: dict[str, str] = {
            f"eval.{suite_id}.cases": "count",
            f"eval.{suite_id}.missing_predictions": "count",
            f"eval.{suite_id}.json_valid_rate": "ratio",
            f"eval.{suite_id}.topic_count_range_accuracy": "ratio",
            f"eval.{suite_id}.fallback_accuracy": "ratio",
            f"eval.{suite_id}.duration_seconds": "s",
        }
        for prefix, source_key in (
            ("strict_membership", "strict_membership"),
            ("semantic_membership", "semantic_membership"),
        ):
            values = summary.get(source_key)
            if not isinstance(values, dict):
                continue
            for metric_key, unit in (
                ("f1", "ratio"),
                ("precision", "ratio"),
                ("recall", "ratio"),
                ("true_positive", "count"),
                ("false_positive", "count"),
                ("false_negative", "count"),
            ):
                metric_name = f"eval.{suite_id}.{prefix}_{metric_key}"
                metrics[metric_name] = float(values.get(metric_key, 0.0) or 0.0)
                units[metric_name] = unit
        bridge_recall = summary.get("bridge_message_recall")
        if isinstance(bridge_recall, dict):
            metric_name = f"eval.{suite_id}.bridge_message_recall"
            metrics[metric_name] = float(bridge_recall.get("recall", 0.0) or 0.0)
            units[metric_name] = "ratio"
        semantic_judge = summary.get("semantic_judge")
        if isinstance(semantic_judge, dict):
            for key in ("calls", "cache_hits", "failures"):
                metric_name = f"eval.{suite_id}.semantic_judge_{key}"
                metrics[metric_name] = float(semantic_judge.get(key, 0.0) or 0.0)
                units[metric_name] = "count"
        return metrics, units

    @staticmethod
    def _topic_membership_compare_summary(
        *,
        job_id: str,
        base_model_id: str,
        target_model_id: str,
        suite_id: str,
        dataset_id: str,
        sample_size: int,
        scoring_mode: str,
        base_run: TopicMembershipRun,
        target_run: TopicMembershipRun,
        compare_samples: tuple[EvaluationCompareSample, ...],
        effect_threshold: float,
        confidence_level: float,
        bootstrap_iterations: int,
        bootstrap_seed: int,
        duration_seconds: float,
        report_path: str,
    ) -> EvaluationCompareSummary:
        win_count = sum(1 for sample in compare_samples if sample.outcome == "win")
        loss_count = sum(1 for sample in compare_samples if sample.outcome == "loss")
        tie_count = sum(1 for sample in compare_samples if sample.outcome == "tie")
        regression_count = sum(1 for sample in compare_samples if sample.regression_kind != "")
        base_metrics = {metric.name: metric.value for metric in getattr(base_run.result, "metrics", ())}
        target_metrics = {metric.name: metric.value for metric in getattr(target_run.result, "metrics", ())}
        primary_suffix = (
            "semantic_membership_f1"
            if scoring_mode == TOPIC_SEMANTIC_SCORING_MODE
            else "strict_membership_f1"
        )
        base_primary = float(getattr(base_run.result, "primary_score_value", 0.0) or 0.0)
        target_primary = float(getattr(target_run.result, "primary_score_value", 0.0) or 0.0)
        delta_primary = round(target_primary - base_primary, 6)
        paired_outcomes = tuple(sample.target_typed_score - sample.base_typed_score for sample in compare_samples)
        statistical_evidence = build_paired_statistical_evidence(
            paired_outcomes=paired_outcomes,
            confidence_level=confidence_level,
            bootstrap_iterations=bootstrap_iterations,
            bootstrap_seed=bootstrap_seed,
        )
        release_gate_summary = classify_release_verdict(
            delta_accuracy=delta_primary,
            effect_threshold=effect_threshold,
            bootstrap_interval=dict(statistical_evidence.get("bootstrap", {})),
            analytical_interval=dict(statistical_evidence.get("analytical", {})),
        )
        metrics: dict[str, float] = {
            "eval.compare.base_accuracy": base_primary,
            "eval.compare.target_accuracy": target_primary,
            "eval.compare.delta_accuracy": delta_primary,
            "eval.compare.base_topic_membership_primary_f1": base_primary,
            "eval.compare.target_topic_membership_primary_f1": target_primary,
            "eval.compare.delta_topic_membership_primary_f1": delta_primary,
            "eval.compare.effect_threshold": float(effect_threshold),
            "eval.compare.win_count": float(win_count),
            "eval.compare.loss_count": float(loss_count),
            "eval.compare.tie_count": float(tie_count),
            "eval.compare.regression_count": float(regression_count),
        }
        units: dict[str, str] = {
            "eval.compare.base_accuracy": "ratio",
            "eval.compare.target_accuracy": "ratio",
            "eval.compare.delta_accuracy": "ratio",
            "eval.compare.base_topic_membership_primary_f1": "ratio",
            "eval.compare.target_topic_membership_primary_f1": "ratio",
            "eval.compare.delta_topic_membership_primary_f1": "ratio",
            "eval.compare.effect_threshold": "ratio",
            "eval.compare.win_count": "count",
            "eval.compare.loss_count": "count",
            "eval.compare.tie_count": "count",
            "eval.compare.regression_count": "count",
        }
        for suffix in (
            "strict_membership_f1",
            "strict_membership_precision",
            "strict_membership_recall",
            "strict_membership_true_positive",
            "strict_membership_false_positive",
            "strict_membership_false_negative",
            "semantic_membership_f1",
            "semantic_membership_precision",
            "semantic_membership_recall",
        ):
            source_name = f"eval.{suite_id}.{suffix}"
            if source_name not in base_metrics and source_name not in target_metrics:
                continue
            base_name = f"eval.compare.base_{suffix}"
            target_name = f"eval.compare.target_{suffix}"
            delta_name = f"eval.compare.delta_{suffix}"
            base_value = float(base_metrics.get(source_name, 0.0) or 0.0)
            target_value = float(target_metrics.get(source_name, 0.0) or 0.0)
            metrics[base_name] = base_value
            metrics[target_name] = target_value
            metrics[delta_name] = round(target_value - base_value, 6)
            unit = "count" if suffix.endswith(("true_positive", "false_positive", "false_negative")) else "ratio"
            units[base_name] = unit
            units[target_name] = unit
            units[delta_name] = unit
        metrics[f"eval.compare.delta_{primary_suffix}"] = delta_primary
        units[f"eval.compare.delta_{primary_suffix}"] = "ratio"
        return build_evaluation_compare_summary_record(
            job_id=job_id,
            base_model_id=base_model_id,
            target_model_id=target_model_id,
            suite_id=suite_id,
            dataset_id=dataset_id,
            sample_size=sample_size,
            scoring_mode=scoring_mode,
            win_count=win_count,
            loss_count=loss_count,
            tie_count=tie_count,
            regression_count=regression_count,
            base_accuracy=base_primary,
            target_accuracy=target_primary,
            delta_accuracy=delta_primary,
            effect_threshold=effect_threshold,
            verdict=str(release_gate_summary["verdict"]),
            category_breakdown={},
            statistical_evidence=statistical_evidence,
            release_gate_summary=release_gate_summary,
            duration_seconds=duration_seconds,
            metrics=metrics,
            report_path=report_path,
            units=units,
        )

    @staticmethod
    def _topic_count_from_output(output_json: dict[str, object]) -> int:
        topics = output_json.get("gold_topics")
        return len(topics) if isinstance(topics, list) else 0


    @staticmethod
    def _read_topic_membership_rows(path: Path, *, sample_size: int) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        with Path(path).open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"expected JSON object at {path}:{line_number}")
                if not isinstance(row.get("source_dialogue_id"), str) or not row.get("source_dialogue_id"):
                    raise ValueError(f"missing source_dialogue_id at {path}:{line_number}")
                if not isinstance(row.get("messages"), list):
                    raise ValueError(f"messages must be a list at {path}:{line_number}")
                if not isinstance(row.get("gold_topics"), list):
                    raise ValueError(f"gold_topics must be a list at {path}:{line_number}")
                normalized = dict(row)
                normalized["messages"] = [
                    {
                        "message_id": str(message.get("message_id") or ""),
                        "sender": str(message.get("sender") or ""),
                        "timestamp": str(message.get("timestamp") or ""),
                        "text": str(message.get("text") or ""),
                    }
                    for message in row.get("messages", [])
                    if isinstance(message, dict)
                ]
                normalized["gold_topics"] = [
                    dict(topic)
                    for topic in row.get("gold_topics", [])
                    if isinstance(topic, dict)
                ]
                rows.append(normalized)
                if sample_size > 0 and len(rows) >= sample_size:
                    break
        if not rows:
            raise ValueError(f"topic membership source JSONL is empty: {path}")
        return rows


    @staticmethod
    def _topic_membership_prompt_spec(parameters: dict[str, str]) -> TopicMembershipPromptSpec:
        system_prompt = str(parameters.get("eval_prompt_system_prompt") or "").strip()
        if not system_prompt:
            raise ValueError("topic_membership scoring requires --eval-prompt-file or --eval-prompt.")
        prompt_id = str(parameters.get("eval_prompt_id") or parameters.get("prompt_id") or "").strip()
        revision_id = str(
            parameters.get("eval_prompt_revision_id") or parameters.get("prompt_revision_id") or ""
        ).strip()
        content_hash = str(
            parameters.get("eval_prompt_content_hash") or parameters.get("prompt_content_hash") or ""
        ).strip()
        if not content_hash:
            content_hash = topic_prompt_content_hash(system_prompt)
        return TopicMembershipPromptSpec(
            prompt_id=prompt_id or TOPIC_MEMBERSHIP_PROMPT_ID,
            revision_id=revision_id or "unknown",
            title=str(parameters.get("eval_prompt_title") or parameters.get("prompt_title") or "").strip(),
            system_prompt=system_prompt,
            content_hash=content_hash,
        )
