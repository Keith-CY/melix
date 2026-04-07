from __future__ import annotations

import gc
import json
from dataclasses import dataclass
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urlparse

from packages.protocol.python.worker.v1 import common_pb2
from worker.productization.benchmark_queue import BenchmarkQueueRecord, BenchmarkQueueStore
from worker.productization.evaluation_schemas import (
    EvaluationJob,
    EvaluationResult,
    EvaluationSample,
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
    "gsm8k": ("exact_match", "exact_match"),
    "humaneval": ("pass_at_1", "pass_at_1"),
    "mbpp": ("pass_at_1", "pass_at_1"),
}
_ARITHMETIC_PROMPT_PATTERN = re.compile(r"\s*(\d+)\s*([+-])\s*(\d+)\s*\?\s*")
_ANSWER_PREFIX_PATTERN = re.compile(
    r"(?im)^\s*(?:final\s+answer|answer|the\s+answer\s+is|answer\s+is)\s*[:\-]?\s*(.+)$",
)
_NUMERIC_TOKEN_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")
_NUMERIC_RESULT_PATTERN = re.compile(r"=\s*([-+]?\d+(?:\.\d+)?)")
_OPTION_TOKEN_PATTERN = re.compile(r"\b([A-Z])\b")
_MULTIMODAL_TASK_KINDS = {"image-to-text", "image-text-to-text"}


@dataclass(frozen=True)
class EvaluationRun:
    job: EvaluationJob
    result: EvaluationResult
    samples: tuple[EvaluationSample, ...]
    persisted_paths: dict[str, Path]


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
    ) -> EvaluationRun:
        dataset_root = Path(dataset_root).resolve()
        if suite_id not in _SUITE_SCORE_MODES:
            raise ValueError(f"Unsupported evaluation suite: {suite_id}")

        manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
        if manifest["suite_id"] != suite_id:
            raise ValueError(
                f"Dataset suite mismatch: expected {suite_id}, found {manifest['suite_id']}"
            )

        samples = [
            json.loads(line)
            for line in (dataset_root / "samples.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        selected = samples[: max(sample_size, 0)]
        score_name, default_scoring_mode = _SUITE_SCORE_MODES[suite_id]
        resolved_scoring_mode = scoring_mode if scoring_mode else default_scoring_mode
        resolved_task_kind = str(
            (parameters or {}).get("task_kind") or manifest.get("task_kind") or "text-generation"
        )
        manifest_input_modalities = tuple(
            str(value)
            for value in manifest.get("input_modalities", [])
            if str(value).strip()
        )
        resolved_few_shot = self._resolve_int_parameter(
            explicit_value=few_shot,
            parameters=parameters,
            key="few_shot",
        )
        resolved_seed = self._resolve_int_parameter(
            explicit_value=seed,
            parameters=parameters,
            key="seed",
        )
        resolved_code_exec_policy = (
            code_exec_policy
            if code_exec_policy is not None and code_exec_policy != ""
            else (parameters or {}).get("code_exec_policy", "")
        )
        created_at_unix_ms = int(time.time() * 1000)
        started_at = time.perf_counter()
        job_id = self._next_job_id()
        run_root = self._run_root(job_id)
        loaded_model = self._loaded_model_for_execution(model_handle)
        resolved_model_id = (
            getattr(getattr(loaded_model, "spec", None), "model_id", "") if loaded_model is not None else ""
        ) or model_id
        sample_records_list: list[EvaluationSample] = []
        for index, sample in enumerate(selected, start=1):
            sample_records_list.append(
                self._build_sample_record(
                    job_id=job_id,
                    suite_id=suite_id,
                    dataset_id=manifest["dataset_id"],
                    task_kind=resolved_task_kind,
                    manifest_input_modalities=manifest_input_modalities,
                    dataset_root=dataset_root,
                    index=index,
                    sample=sample,
                    loaded_model=loaded_model,
                )
            )
            if loaded_model is not None:
                self._release_runtime_memory()
        sample_records = tuple(sample_records_list)
        duration_seconds = round(time.perf_counter() - started_at, 6)
        correct = sum(1 for sample in sample_records if sample.correct)
        incorrect = len(sample_records) - correct
        accuracy = round(correct / max(len(sample_records), 1), 4)
        job_parameters = {"dataset_root": str(dataset_root)}
        if parameters:
            job_parameters.update(parameters)
        job_parameters.setdefault("task_kind", resolved_task_kind)
        job_parameters["few_shot"] = str(resolved_few_shot)
        job_parameters["seed"] = str(resolved_seed)
        job_parameters["scoring_mode"] = resolved_scoring_mode
        job_parameters["code_exec_policy"] = resolved_code_exec_policy
        job_parameters.setdefault("sample_size", str(len(sample_records)))

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
            score_name=score_name,
            score_value=accuracy,
            correct_count=correct,
            incorrect_count=incorrect,
            duration_seconds=duration_seconds,
            metrics={
                f"eval.{suite_id}.{score_name}": accuracy,
                f"eval.{suite_id}.correct_count": float(correct),
                f"eval.{suite_id}.incorrect_count": float(incorrect),
                f"eval.{suite_id}.duration_seconds": duration_seconds,
            },
            report_path=str(report_path),
            units={
                f"eval.{suite_id}.{score_name}": "ratio",
                f"eval.{suite_id}.correct_count": "count",
                f"eval.{suite_id}.incorrect_count": "count",
                f"eval.{suite_id}.duration_seconds": "s",
            },
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
        return EvaluationRun(job=job, result=result, samples=sample_records, persisted_paths=persisted_paths)

    def _result_path(self, run_root: Path) -> Path:
        if self._jobs_root is not None:
            return run_root / "evaluation-result.json"
        return run_root / "evaluation-result.json"

    def _next_job_id(self) -> str:
        if self._jobs_root is None:
            return "eval-local"
        runs_root = self._jobs_root / "runs"
        runs_root.mkdir(parents=True, exist_ok=True)
        existing = sorted(
            int(path.name.removeprefix("eval-"))
            for path in runs_root.iterdir()
            if path.is_dir() and path.name.startswith("eval-") and path.name.removeprefix("eval-").isdigit()
        )
        next_index = (existing[-1] + 1) if existing else 1
        return f"eval-{next_index:04d}"

    def _run_root(self, job_id: str) -> Path:
        if self._jobs_root is None:
            return Path.cwd()
        return self._jobs_root / "runs" / job_id

    def _loaded_model_for_execution(self, model_handle: str | None):
        if not model_handle or self._registry is None:
            return None
        return self._registry.get_loaded_model(model_handle)

    @staticmethod
    def _resolve_int_parameter(
        *,
        explicit_value: int | None,
        parameters: dict[str, str] | None,
        key: str,
    ) -> int:
        if explicit_value is not None:
            return int(explicit_value)
        raw_value = (parameters or {}).get(key)
        if raw_value is None or raw_value == "":
            return 0
        try:
            return int(raw_value)
        except ValueError:
            return 0

    def _build_sample_record(
        self,
        *,
        job_id: str,
        suite_id: str,
        dataset_id: str,
        task_kind: str,
        manifest_input_modalities: tuple[str, ...],
        dataset_root: Path,
        index: int,
        sample: dict[str, object],
        loaded_model=None,
    ) -> EvaluationSample:
        prompt = str(sample.get("prompt", sample.get("question", "")))
        expected = str(sample.get("expected", sample.get("answer", ""))).strip()
        media_references = EvaluationCore._media_references_for_sample(
            task_kind=task_kind,
            dataset_root=dataset_root,
            sample=sample,
        )
        input_modalities = EvaluationCore._input_modalities_for_sample(
            task_kind=task_kind,
            prompt=prompt,
            media_references=media_references,
            manifest_input_modalities=manifest_input_modalities,
        )
        started_at = time.perf_counter()
        raw_response = ""
        if loaded_model is not None:
            raw_response = EvaluationCore._execute_live_prompt(
                registry=self._registry,
                loaded_model=loaded_model,
                messages=EvaluationCore._evaluation_messages(
                    prompt=prompt,
                    expected=expected,
                    media_references=media_references,
                ),
                expected=expected,
                request_id=f"eval:{job_id}:{suite_id}:{sample.get('id', index)}",
            )
            predicted, parse_status = EvaluationCore._parse_prediction(
                suite_id=suite_id,
                raw_response=raw_response,
                expected=expected,
            )
        else:
            if task_kind in _MULTIMODAL_TASK_KINDS:
                predicted = ""
                parse_status = "unsupported_multimodal_offline"
            else:
                predicted = EvaluationCore._deterministic_answer(prompt)
                raw_response = predicted
                parse_status = "parsed" if predicted else "empty_prediction"
        duration_s = round(time.perf_counter() - started_at, 6)
        return build_evaluation_sample_record(
            job_id=job_id,
            suite_id=suite_id,
            dataset_id=dataset_id,
            sample_id=str(sample.get("id", index)),
            question=prompt,
            expected=expected,
            predicted=predicted,
            raw_response=raw_response,
            correct=EvaluationCore._answers_match(expected=expected, predicted=predicted),
            time_s=duration_s,
            parse_status=parse_status,
            task_kind=task_kind,
            input_modalities=input_modalities,
            media_references=media_references,
        )

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
        request_id: str,
    ) -> str:
        runtime = registry.runtime_for_loaded_model(loaded_model)
        state = registry.start_request(request_id, runtime_kind=loaded_model.runtime_kind)
        chunks: list[str] = []
        try:
            rendered_prompt = runtime.render_prompt(
                messages,
                loaded_model=loaded_model.runtime_model,
                execution_ext={},
            )
            sampling = common_pb2.SamplingConfig(
                temperature=0.0,
                top_p=1.0,
                top_k=1,
                max_output_tokens=EvaluationCore._evaluation_max_output_tokens(expected),
            )
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
        finally:
            if loaded_model.runtime_kind in {"ocr", "vlm"} and hasattr(runtime, "last_probe_snapshot"):
                registry.record_vision_probe(loaded_model.runtime_kind, runtime.last_probe_snapshot())
            registry.finish_request(request_id)
        return "".join(chunks).strip()

    @staticmethod
    def _evaluation_messages(
        prompt: str,
        expected: str,
        media_references: tuple[str, ...] = (),
    ) -> list[common_pb2.ChatMessage]:
        if EvaluationCore._looks_like_numeric(expected):
            instruction = "Return only the final numeric answer. Do not include reasoning or explanation."
        elif EvaluationCore._looks_like_option(expected):
            instruction = "Return only the single best answer choice letter. Do not include reasoning or explanation."
        else:
            instruction = "Return only the final short answer. Do not include reasoning or explanation."
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
        return [
            common_pb2.ChatMessage(role="system", parts=[common_pb2.MessagePart(text=instruction)]),
            common_pb2.ChatMessage(role="user", parts=user_parts),
        ]

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

        def append_reference(value: object) -> None:
            if isinstance(value, str) and value.strip():
                references.append(
                    EvaluationCore._resolved_media_reference(
                        dataset_root=dataset_root,
                        value=value,
                    )
                )

        append_reference(sample.get("image_uri"))
        for key in ("image_uris", "images"):
            raw_value = sample.get(key)
            if isinstance(raw_value, (list, tuple)):
                for item in raw_value:
                    append_reference(item)
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
    def _evaluation_max_output_tokens(expected: str) -> int:
        if EvaluationCore._looks_like_numeric(expected) or EvaluationCore._looks_like_option(expected):
            return 32
        return 128

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

        answer_matches = list(_ANSWER_PREFIX_PATTERN.finditer(normalized_response))
        answer_match = answer_matches[-1] if answer_matches else None
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
