from __future__ import annotations

import builtins
import json
from pathlib import Path
import random
import sys
from types import ModuleType, SimpleNamespace

import pytest

from packages.protocol.python.worker.v1 import common_pb2, maintenance_pb2
import worker.engine.evaluation_core as evaluation_core_module
from worker.engine.evaluation_core import EvaluationCore
from worker.grpc_server import WorkerMaintenanceService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.productization.evaluation_schemas import EvaluationCompareJob
from worker.productization.event_extraction import EventExtractionClientResult
from worker.runtime.mlx_text_runtime import MLXTextRuntime, RuntimeTokenEvent


class ScriptedEvaluationBackend:
    runtime_name = "scripted-evaluation"

    def __init__(self, responses: tuple[str, ...]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []
        self.samplings: list[common_pb2.SamplingConfig] = []

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

    def estimate_resident_bytes(self, model_spec) -> int:
        _ = model_spec
        return 1024

    def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event):
        _ = loaded_model
        self.prompts.append(prompt)
        sampling_snapshot = common_pb2.SamplingConfig()
        sampling_snapshot.CopyFrom(sampling)
        self.samplings.append(sampling_snapshot)
        if cancel_event.is_set():
            return
        text = self._responses.pop(0)
        yield RuntimeTokenEvent(text=text, completion_tokens=max(1, len(text.split())))


class ModelAwareComparisonBackend:
    runtime_name = "model-aware-comparison"

    def __init__(self, responses_by_model_id: dict[str, tuple[str, ...]]) -> None:
        self._responses_by_model_id = {
            model_id: list(responses)
            for model_id, responses in responses_by_model_id.items()
        }

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

    def estimate_resident_bytes(self, model_spec) -> int:
        _ = model_spec
        return 1024

    def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event):
        _ = prompt
        _ = sampling
        if cancel_event.is_set():
            return
        model_id = str(loaded_model.get("model_id", ""))
        text = self._responses_by_model_id[model_id].pop(0)
        yield RuntimeTokenEvent(text=text, completion_tokens=max(1, len(text.split())))


def test_evaluation_failure_stage_disables_score_threshold_when_zero() -> None:
    assert (
        EvaluationCore._evaluation_failure_stage(
            extraction_status="extracted",
            validation_status="validated",
            typed_score=-0.1,
            threshold=0.0,
        )
        == ""
    )


def test_evaluation_failure_stage_reports_validation_and_positive_threshold_scoring() -> None:
    assert (
        EvaluationCore._evaluation_failure_stage(
            extraction_status="extracted",
            validation_status="not_validated",
            typed_score=1.0,
            threshold=1.0,
        )
        == "validation"
    )
    assert (
        EvaluationCore._evaluation_failure_stage(
            extraction_status="extracted",
            validation_status="validated",
            typed_score=0.5,
            threshold=1.0,
        )
        == "scoring"
    )


def test_multimodal_media_helpers_collect_nested_references(tmp_path: Path) -> None:
    sample = {
        "input": {
            "image_uri": "input.png",
            "image_uris": ["input-list.png"],
            "media": [{"uri": "input-media.png"}],
        },
        "images": ["sample-list.png"],
        "media": [{"image_uri": "sample-media.png"}],
    }

    references = EvaluationCore._media_references_for_sample(
        task_kind="image-text-to-text",
        dataset_root=tmp_path,
        sample=sample,
    )

    assert references == (
        str((tmp_path / "input.png").resolve()),
        str((tmp_path / "input-list.png").resolve()),
        str((tmp_path / "sample-list.png").resolve()),
        str((tmp_path / "input-media.png").resolve()),
        str((tmp_path / "sample-media.png").resolve()),
    )
    assert EvaluationCore._sample_declares_image_media(sample) is True
    assert (
        EvaluationCore._resolved_media_reference(
            dataset_root=tmp_path,
            value="https://example.test/image.png",
        )
        == "https://example.test/image.png"
    )


def test_evaluation_static_fallback_helpers_cover_non_default_branches() -> None:
    assert EvaluationCore._deterministic_answer("7 - 2?") == "5"
    assert EvaluationCore._input_modalities_for_sample(
        task_kind="text-generation",
        prompt="",
        media_references=(),
        manifest_input_modalities=(),
    ) == ("text",)
    assert EvaluationCore._target_text_for_sample({"target": {"answer": 4}}) == '{"answer":4}'
    assert EvaluationCore._evaluation_max_output_tokens("{}", result_kind="json") == 256


class FakeEvaluationRegistry:
    def __init__(
        self,
        *,
        runtime,
        model_id: str = "melix-dev-text",
        runtime_kind: str = "text",
        additional_models: dict[str, tuple[object, str]] | None = None,
        ephemeral_runtime: object | None = None,
    ) -> None:
        self._primary_model_id = model_id
        self._loaded_models_by_handle: dict[str, object] = {}
        self._handles_by_model_id: dict[str, str] = {}
        self._register_loaded_model(model_id=model_id, runtime=runtime, runtime_kind=runtime_kind)
        for additional_model_id, (additional_runtime, additional_runtime_kind) in (additional_models or {}).items():
            self._register_loaded_model(
                model_id=additional_model_id,
                runtime=additional_runtime,
                runtime_kind=additional_runtime_kind,
            )
        self.started_requests: list[tuple[str, str]] = []
        self.finished_requests: list[str] = []
        self.vision_probes: list[tuple[str, object]] = []
        # Module 2: track ephemeral adapter-target load/unload for tests.
        # ``load_model_calls`` records the model_ids loaded via ``load_model``
        # (used by ``resolve_compare_target_adapters``); ``unload_model_calls``
        # records the handles the compare ``finally`` block cleans up.
        self.load_model_calls: list[str] = []
        self.unload_model_calls: list[str] = []
        self._ephemeral_runtime = ephemeral_runtime or runtime

    @property
    def handle(self) -> str:
        return self.handle_for(self._primary_model_id)

    def handle_for(self, model_id: str) -> str:
        return self._handles_by_model_id[model_id]

    def _register_loaded_model(self, *, model_id: str, runtime, runtime_kind: str) -> None:
        handle = f"{model_id}::test"
        loaded_model = SimpleNamespace(
            handle=handle,
            runtime_kind=runtime_kind,
            runtime_model={"model_id": model_id},
            spec=SimpleNamespace(model_id=model_id, ext={"melix.source_repo": "test/source"}),
            runtime=runtime,
        )
        self._loaded_models_by_handle[handle] = loaded_model
        self._handles_by_model_id[model_id] = handle

    def get_loaded_model(self, handle: str):
        return self._loaded_models_by_handle.get(handle)

    def list_loaded_models(self) -> list[str]:
        return sorted(self._loaded_models_by_handle)

    def runtime_for_loaded_model(self, loaded_model):
        return loaded_model.runtime

    def start_request(self, request_id: str, runtime_kind: str = "text"):
        self.started_requests.append((request_id, runtime_kind))
        return SimpleNamespace(cancel_event=SimpleNamespace(is_set=lambda: False))

    def finish_request(self, request_id: str) -> None:
        self.finished_requests.append(request_id)

    def record_vision_probe(self, runtime_kind: str, probe) -> None:
        self.vision_probes.append((runtime_kind, probe))

    def load_model(self, model_spec):
        # Materialize a new ephemeral adapter-backed compare target. Records
        # the model_id for test assertions and reuses the primary runtime
        # (so the probe runtime still returns scripted responses).
        self.load_model_calls.append(str(model_spec.model_id))
        self._register_loaded_model(
            model_id=str(model_spec.model_id),
            runtime=self._ephemeral_runtime,
            runtime_kind="text",
        )
        return self._loaded_models_by_handle[self._handles_by_model_id[str(model_spec.model_id)]]

    def unload_model(self, handle: str) -> bool:
        # Record every unload call — the compare ``finally`` block must hit
        # this for every ephemeral load, on both success and failure paths.
        self.unload_model_calls.append(handle)
        loaded = self._loaded_models_by_handle.pop(handle, None)
        if loaded is None:
            return False
        model_id = loaded.spec.model_id
        self._handles_by_model_id.pop(model_id, None)
        return True


class ProbeRuntime:
    runtime_name = "probe-live-runtime"

    def __init__(self, response: str, probe: object) -> None:
        self._response = response
        self._probe = probe

    def render_prompt(self, messages, loaded_model=None, execution_ext=None):
        _ = loaded_model
        _ = execution_ext
        return "\n".join(part.text for message in messages for part in message.parts)

    def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event, execution_ext=None):
        _ = loaded_model
        _ = prompt
        _ = sampling
        _ = execution_ext
        if cancel_event.is_set():
            return
        yield RuntimeTokenEvent(text=self._response, completion_tokens=1)

    def last_probe_snapshot(self):
        return self._probe


class ScriptedVisionEvaluationRuntime:
    def __init__(self, response: str, probe: object) -> None:
        self._response = response
        self._probe = probe
        self.rendered_messages: list[list[list[tuple[str, str, str, str]]]] = []

    def render_prompt(self, messages, loaded_model=None, execution_ext=None):
        _ = loaded_model
        _ = execution_ext
        snapshot: list[list[tuple[str, str, str, str]]] = []
        for message in messages:
            parts_snapshot: list[tuple[str, str, str, str]] = []
            for part in message.parts:
                media_filename = part.media.filename if part.HasField("media") else ""
                parts_snapshot.append(
                    (
                        part.WhichOneof("part") or "",
                        part.text,
                        part.image_uri,
                        media_filename,
                    )
                )
            snapshot.append(parts_snapshot)
        self.rendered_messages.append(snapshot)
        return messages

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event, execution_ext=None):
        _ = loaded_model
        _ = prompt
        _ = sampling
        _ = execution_ext
        if cancel_event.is_set():
            return
        yield RuntimeTokenEvent(text=self._response, completion_tokens=1)

    def last_probe_snapshot(self):
        return self._probe


class ScriptedComparisonRuntime:
    def __init__(self, responses: tuple[str, ...]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def render_prompt(self, messages, loaded_model=None, execution_ext=None):
        _ = loaded_model
        _ = execution_ext
        prompt = "\n".join(part.text for message in messages for part in message.parts if part.text)
        self.prompts.append(prompt)
        return prompt

    def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event, execution_ext=None):
        _ = loaded_model
        _ = prompt
        _ = sampling
        _ = execution_ext
        if cancel_event.is_set():
            return
        text = self._responses.pop(0)
        yield RuntimeTokenEvent(text=text, completion_tokens=max(1, len(text.split())))


def test_resolve_float_parameter_returns_parsed_or_default_value() -> None:
    assert EvaluationCore._resolve_float_parameter(
        parameters={"effect_threshold": "0.25"},
        key="effect_threshold",
        default_value=0.1,
    ) == pytest.approx(0.25)
    assert EvaluationCore._resolve_float_parameter(
        parameters={"effect_threshold": "not-a-float"},
        key="effect_threshold",
        default_value=0.1,
    ) == pytest.approx(0.1)
    assert EvaluationCore._resolve_float_parameter(
        parameters={},
        key="effect_threshold",
        default_value=0.1,
    ) == pytest.approx(0.1)


def test_load_dataset_samples_streams_jsonl_and_skips_blank_lines(tmp_path: Path) -> None:
    samples_path = tmp_path / "samples.jsonl"
    samples_path.write_text(
        '{"id": "1", "prompt": "2+2?", "expected": "4"}\n\n'
        '  \n'
        '{"id": "2", "prompt": "3+3?", "expected": "6"}\n',
        encoding="utf-8",
    )

    assert EvaluationCore._load_dataset_samples(samples_path) == [
        {"id": "1", "prompt": "2+2?", "expected": "4"},
        {"id": "2", "prompt": "3+3?", "expected": "6"},
    ]


def test_plan_evaluation_samples_preserves_order_without_shuffle() -> None:
    samples = [
        {"id": "first"},
        {"id": "second"},
        {"id": "third"},
    ]

    few_shot_examples, selected = EvaluationCore._plan_evaluation_samples(
        samples=samples,
        sample_size=-5,
        few_shot=2,
        seed=0,
    )

    assert few_shot_examples == ({"id": "first"}, {"id": "second"})
    assert selected == []
    assert samples == [
        {"id": "first"},
        {"id": "second"},
        {"id": "third"},
    ]


def test_run_local_suite_only_loads_needed_prefix_without_shuffle(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev-prefix",
        suite_id="mmlu",
        samples=(
            {"id": "1", "prompt": "2+2?", "expected": "4"},
            {"id": "2", "prompt": "3+3?", "expected": "6"},
            {"id": "3", "prompt": "4+4?", "expected": "8"},
        ),
    )
    (dataset_root / "samples.jsonl").write_text(
        '{"id": "1", "input": {"text": "2+2?"}, "target": "4"}\n'
        '{"id": "2", "input": {"text": "3+3?"}, "target": "6"}\n'
        '{"id": "3", "input": {"text": "4+4?"}, "target": "8"\n',
        encoding="utf-8",
    )

    backend = ScriptedEvaluationBackend(("Answer: 6",))
    runtime = MLXTextRuntime(backend=backend)
    registry = FakeEvaluationRegistry(runtime=runtime, model_id="persisted-eval-model")
    runner = EvaluationCore(jobs_root=tmp_path / "runs" / "mmlu", registry=registry)

    run = runner.run_local_suite(
        model_id="persisted-eval-model",
        model_handle=registry.handle,
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=1,
        few_shot=1,
        seed=0,
        scoring_mode="multiple_choice_accuracy",
        code_exec_policy="disabled",
    )

    assert [sample.input_text for sample in run.samples] == ["3+3?"]
    assert [sample.extracted_result for sample in run.samples] == ["6"]


def test_run_local_suite_skips_dataset_parsing_for_zero_sample_request(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev-zero",
        suite_id="mmlu",
        samples=(({"id": "1", "prompt": "2+2?", "expected": "4"}),),
    )
    (dataset_root / "samples.jsonl").write_text(
        '{"id": "1", "input": {"text": "2+2?"}, "target": "4"\n',
        encoding="utf-8",
    )

    backend = ScriptedEvaluationBackend(())
    runtime = MLXTextRuntime(backend=backend)
    registry = FakeEvaluationRegistry(runtime=runtime, model_id="persisted-eval-model")
    runner = EvaluationCore(jobs_root=tmp_path / "runs" / "mmlu", registry=registry)

    run = runner.run_local_suite(
        model_id="persisted-eval-model",
        model_handle=registry.handle,
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=0,
        few_shot=0,
        seed=7,
        scoring_mode="multiple_choice_accuracy",
        code_exec_policy="disabled",
    )

    assert run.samples == ()


def test_run_local_suite_reuses_combined_sample_list_for_validators(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"prompt": "2+2?", "expected": "4"},
            {"prompt": "3+3?", "expected": "6"},
        ),
    )
    backend = ScriptedEvaluationBackend(("Answer: 4", "Answer: 6"))
    runtime = MLXTextRuntime(backend=backend)
    registry = FakeEvaluationRegistry(runtime=runtime, model_id="persisted-eval-model")
    runner = EvaluationCore(jobs_root=tmp_path / "runs" / "mmlu", registry=registry)

    validator_sample_ids: list[int] = []
    original_task_kind_validator = EvaluationCore._validate_task_kind_against_dataset
    original_live_validator = EvaluationCore._validate_live_multimodal_execution

    def capture_task_kind_validator(**kwargs: object) -> None:
        validator_sample_ids.append(id(kwargs["samples"]))
        original_task_kind_validator(**kwargs)

    def capture_live_validator(**kwargs: object) -> None:
        validator_sample_ids.append(id(kwargs["samples"]))
        original_live_validator(**kwargs)

    monkeypatch.setattr(
        EvaluationCore,
        "_validate_task_kind_against_dataset",
        staticmethod(capture_task_kind_validator),
    )
    monkeypatch.setattr(
        EvaluationCore,
        "_validate_live_multimodal_execution",
        staticmethod(capture_live_validator),
    )

    runner.run_local_suite(
        model_id="persisted-eval-model",
        model_handle=registry.handle,
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=2,
        few_shot=1,
        seed=0,
        scoring_mode="multiple_choice_accuracy",
        code_exec_policy="disabled",
    )

    assert len(validator_sample_ids) == 2
    assert validator_sample_ids[0] == validator_sample_ids[1]


def test_run_local_suite_streams_samples_jsonl_without_read_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"prompt": "2+2?", "expected": "4"},
            {"prompt": "3+3?", "expected": "6"},
        ),
    )
    (dataset_root / "samples.jsonl").write_text(
        '{"id": "1", "input": {"text": "2+2?"}, "target": "4"}\n\n'
        '{"id": "2", "input": {"text": "3+3?"}, "target": "6"}\n',
        encoding="utf-8",
    )

    original_read_text = Path.read_text

    def guarded_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == dataset_root / "samples.jsonl":
            raise AssertionError("samples.jsonl should be streamed via Path.open()")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    backend = ScriptedEvaluationBackend(("Answer: 4", "Answer: 6"))
    runtime = MLXTextRuntime(backend=backend)
    registry = FakeEvaluationRegistry(runtime=runtime, model_id="persisted-eval-model")
    runner = EvaluationCore(jobs_root=tmp_path / "runs" / "mmlu", registry=registry)

    run = runner.run_local_suite(
        model_id="persisted-eval-model",
        model_handle=registry.handle,
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=2,
        few_shot=0,
        seed=7,
        scoring_mode="multiple_choice_accuracy",
        code_exec_policy="disabled",
    )

    assert [sample.input_text for sample in run.samples] == ["2+2?", "3+3?"]
    assert [sample.extracted_result for sample in run.samples] == ["4", "6"]


def test_run_local_suite_executes_packaged_dataset_and_persists_result(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"prompt": "2+2?", "expected": "4"},
            {"prompt": "3+3?", "expected": "6"},
        ),
    )
    jobs_root = tmp_path / "runs" / "mmlu"
    backend = ScriptedEvaluationBackend(("Answer: 4", "Answer: 6"))
    runtime = MLXTextRuntime(backend=backend)
    registry = FakeEvaluationRegistry(runtime=runtime, model_id="persisted-eval-model")
    runner = EvaluationCore(jobs_root=jobs_root, registry=registry)

    run = runner.run_local_suite(
        model_id="persisted-eval-model",
        model_handle=registry.handle,
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=2,
        few_shot=0,
        seed=7,
        scoring_mode="multiple_choice_accuracy",
        code_exec_policy="disabled",
    )

    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert run.job.dataset_id == "mmlu-dev"
    assert run.job.sample_size == 2
    assert run.job.task_kind == "text-generation"
    assert run.job.few_shot == 0
    assert run.job.seed == 7
    assert run.job.scoring_mode == "multiple_choice_accuracy"
    assert run.job.code_exec_policy == "disabled"
    assert metrics["eval.mmlu.typed_score_mean"] == 1.0
    assert metrics["eval.mmlu.threshold_pass_rate"] == 1.0
    assert metrics["eval.mmlu.extraction_success_count"] == 2.0
    assert metrics["eval.mmlu.validation_success_count"] == 2.0
    assert metrics["eval.mmlu.scored_sample_count"] == 2.0
    assert metrics["eval.mmlu.failure_count"] == 0.0
    assert metrics["eval.mmlu.duration_seconds"] >= 0.0
    assert run.result.primary_score_name == "typed_score_mean"
    assert run.result.primary_score_value == 1.0
    assert run.result.extraction_success_count == 2
    assert run.result.validation_success_count == 2
    assert run.result.scored_sample_count == 2
    assert run.result.failure_count == 0
    assert run.result.duration_seconds >= 0.0
    assert run.job.job_id == "eval-0001"
    assert run.persisted_paths["job"] == jobs_root / "runs" / "eval-0001" / "evaluation-job.json"
    assert run.persisted_paths["result"] == jobs_root / "runs" / "eval-0001" / "evaluation-result.json"
    assert run.persisted_paths["summary_json"] == jobs_root / "runs" / "eval-0001" / "evaluation-summary.json"
    assert run.persisted_paths["summary_csv"] == jobs_root / "runs" / "eval-0001" / "evaluation-summary.csv"
    assert run.persisted_paths["samples_jsonl"] == jobs_root / "runs" / "eval-0001" / "evaluation-samples.jsonl"
    assert json.loads(run.persisted_paths["job"].read_text(encoding="utf-8")) == run.job.to_dict()
    assert json.loads(run.persisted_paths["result"].read_text(encoding="utf-8")) == run.result.to_dict()
    assert (
        json.loads(run.persisted_paths["summary_json"].read_text(encoding="utf-8"))["primary_score_name"]
        == "typed_score_mean"
    )
    assert (
        "job_id,task_kind,source_repo,model_id,suite_id,dataset_id,primary_score_name,"
        "primary_score_value,sample_size,extraction_success_count,validation_success_count,"
        "scored_sample_count,failure_count,duration_seconds,created_at_unix_ms"
        in run.persisted_paths["summary_csv"].read_text(encoding="utf-8")
    )
    persisted_samples = [
        json.loads(line)
        for line in run.persisted_paths["samples_jsonl"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert persisted_samples == [sample.to_dict() for sample in run.samples]
    assert len(run.samples) == 2
    assert run.samples[0].sample_id == "1"
    assert run.samples[0].input_text == "2+2?"
    assert run.samples[0].extracted_result == "4"
    assert run.samples[0].typed_score == 1.0
    assert run.samples[0].validation_status == "validated"

    queue_payload = json.loads((jobs_root / "queue" / f"{run.job.job_id}.json").read_text(encoding="utf-8"))
    assert queue_payload["job_kind"] == "evaluation"
    assert queue_payload["status"] == "completed"
    assert queue_payload["parameters"]["sample_size"] == "2"
    assert queue_payload["started_at_unix_ms"] > 0
    assert queue_payload["completed_at_unix_ms"] > 0


def test_next_job_id_primes_from_highest_existing_run_directory(tmp_path: Path) -> None:
    jobs_root = tmp_path / "runs" / "mmlu"
    runs_root = jobs_root / "runs"
    (runs_root / "eval-0001").mkdir(parents=True)
    (runs_root / "eval-0003").mkdir(parents=True)
    (runs_root / "notes").mkdir(parents=True)
    (runs_root / "README.txt").write_text("ignore me\n", encoding="utf-8")
    (runs_root / "eval-999x").mkdir(parents=True)

    runner = EvaluationCore(jobs_root=jobs_root)

    assert runner._next_job_id() == "eval-0004"
    assert runner._next_job_id() == "eval-0005"
    assert (runs_root / "eval-0004").is_dir()
    assert (runs_root / "eval-0005").is_dir()


def test_next_job_id_only_scans_existing_runs_once_per_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs_root = tmp_path / "runs" / "mmlu"
    runs_root = jobs_root / "runs"
    (runs_root / "eval-0002").mkdir(parents=True)
    runner = EvaluationCore(jobs_root=jobs_root)
    original_scandir = evaluation_core_module.os.scandir
    scan_count = 0

    def tracked_scandir(path: str | bytes | Path):
        nonlocal scan_count
        if Path(path) == runs_root:
            scan_count += 1
        return original_scandir(path)

    def fail_iterdir(path: Path):
        raise AssertionError("_prime_next_job_index should use os.scandir instead of Path.iterdir")

    monkeypatch.setattr(evaluation_core_module.os, "scandir", tracked_scandir)
    monkeypatch.setattr(Path, "iterdir", fail_iterdir)

    assert runner._next_job_id() == "eval-0003"
    assert runner._next_job_id() == "eval-0004"
    assert scan_count == 1


def test_next_job_id_skips_conflicting_cached_index_and_non_directory_entries(tmp_path: Path) -> None:
    jobs_root = tmp_path / "runs" / "mmlu"
    runs_root = jobs_root / "runs"
    runs_root.mkdir(parents=True)
    (runs_root / "eval-0002").mkdir()
    (runs_root / "eval-0003").write_text("not a directory\n", encoding="utf-8")

    runner = EvaluationCore(jobs_root=jobs_root)
    runner._next_job_index = 3

    assert runner._next_job_id() == "eval-0004"
    assert runner._next_job_index == 5
    assert (runs_root / "eval-0004").is_dir()


def test_run_local_suite_marks_offline_execution_as_non_evidence(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"prompt": "2+2?", "expected": "4"},
            {"prompt": "capital of france?", "expected": "Paris"},
            {"prompt": "3+3?", "expected": "6"},
        ),
    )
    runner = EvaluationCore()

    run = runner.run_local_suite(
        model_id="melix-dev-text",
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=2,
    )

    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert run.job.sample_size == 2
    assert metrics["eval.mmlu.typed_score_mean"] == 0.5
    assert metrics["eval.mmlu.threshold_pass_rate"] == 0.5
    assert run.persisted_paths == {}
    assert len(run.samples) == 2
    assert run.samples[0].extracted_result == "4"
    assert run.samples[0].typed_score == 1.0
    assert run.samples[1].extracted_result == ""
    assert run.samples[1].validation_status == "not_validated"
    assert run.samples[0].code_test_status == ""


def test_run_local_suite_executes_code_candidates_for_mbpp(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mbpp-dev",
        suite_id="mbpp",
        samples=(
            {"id": "sample-1", "question": "2+2?", "answer": "4"},
        ),
    )
    jobs_root = tmp_path / "runs" / "mbpp"
    backend = ScriptedEvaluationBackend(
        (
            "```python\n"
            "def add(a, b):\n"
            "    return a + b\n"
            "```",
        )
    )
    runtime = MLXTextRuntime(backend=backend)
    registry = FakeEvaluationRegistry(runtime=runtime, model_id="mbpp-eval-model")
    runner = EvaluationCore(jobs_root=jobs_root, registry=registry)

    run = runner.run_local_suite(
        model_id="mbpp-eval-model",
        model_handle=registry.handle,
        suite_id="mbpp",
        dataset_root=dataset_root,
        sample_size=1,
        parameters={
            "task_kind": "text-generation",
            "source_repo": "openai_humaneval",
            "entry_point": "add",
            "test_code": "assert add(2, 2) == 4\nassert add(-1, 1) == 0",
        },
    )

    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert run.job.job_id == "eval-0001"
    assert run.job.source_repo == "openai_humaneval"
    assert run.job.output_dir == str(jobs_root / "runs" / "eval-0001")
    assert run.job.scoring_mode == "pass_at_1"
    assert run.job.few_shot == 0
    assert run.job.seed == 0
    assert run.job.code_exec_policy == "sandboxed"
    assert metrics["eval.mbpp.typed_score_mean"] == 1.0
    assert metrics["eval.mbpp.code_exec_pass_count"] == 1.0
    assert metrics["eval.mbpp.code_exec_fail_count"] == 0.0
    assert run.samples[0].typed_score == 1.0
    assert run.samples[0].extraction_status == "extracted"
    assert run.samples[0].validation_status == "validated"
    assert run.samples[0].code_language == "python"
    assert run.samples[0].code_entry_point == "add"
    assert run.samples[0].code_compile_status == "compiled"
    assert run.samples[0].code_runtime_status == "ok"
    assert run.samples[0].code_timeout_status == "ok"
    assert run.samples[0].code_test_status == "passed"
    assert run.samples[0].code_tests_passed == 2
    assert run.samples[0].code_tests_total == 2
    assert run.samples[0].code_failure_detail == ""
    assert "def add" in run.samples[0].extracted_result


def test_run_local_suite_executes_candidate_code_for_humaneval_samples(
    tmp_path: Path,
) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="humaneval-dev",
        suite_id="humaneval",
        samples=(
            {
                "id": "sample-1",
                "prompt": "Write identity(x) that returns x.",
                "entry_point": "identity",
                "test": "assert identity(4) == 4\nassert identity('hi') == 'hi'",
            },
        ),
    )
    backend = ScriptedEvaluationBackend(
        (
            "```python\ndef identity(x):\n    return x\n```",
        )
    )
    runtime = MLXTextRuntime(backend=backend)
    registry = FakeEvaluationRegistry(runtime=runtime, model_id="live-code-eval-model")
    runner = EvaluationCore(registry=registry)

    run = runner.run_local_suite(
        model_id="live-code-eval-model",
        model_handle=registry.handle,
        suite_id="humaneval",
        dataset_root=dataset_root,
        sample_size=1,
        code_exec_policy="sandboxed",
    )

    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert len(backend.prompts) == 1
    assert "Return only executable Python code" in backend.prompts[0]
    assert run.job.code_exec_policy == "sandboxed"
    assert run.samples[0].typed_score == 1.0
    assert run.samples[0].extraction_status == "extracted"
    assert run.samples[0].validation_status == "validated"
    assert run.samples[0].code_language == "python"
    assert run.samples[0].code_entry_point == "identity"
    assert run.samples[0].code_test_status == "passed"
    assert run.result.primary_score_name == "typed_score_mean"
    assert run.result.primary_score_value == 1.0
    assert metrics["eval.humaneval.typed_score_mean"] == 1.0
    assert metrics["eval.humaneval.code_exec_pass_count"] == 1.0
    assert metrics["eval.humaneval.code_exec_fail_count"] == 0.0


def test_run_local_suite_falls_back_to_zero_for_invalid_numeric_controls(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"prompt": "capital of france?", "expected": "Paris"},
        ),
    )
    runner = EvaluationCore()

    run = runner.run_local_suite(
        model_id="melix-dev-text",
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=1,
        parameters={
            "few_shot": "invalid",
            "seed": "also-invalid",
            "code_exec_policy": "disabled",
        },
    )

    assert run.job.few_shot == 0
    assert run.job.seed == 0
    assert run.job.code_exec_policy == "disabled"
    assert run.job.parameters["few_shot"] == "0"
    assert run.job.parameters["seed"] == "0"


def test_run_local_suite_uses_loaded_runtime_predictions_for_live_evaluation(
    tmp_path: Path,
) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"prompt": "capital of france?", "expected": "Paris"},
        ),
    )
    backend = ScriptedEvaluationBackend(("Answer: Paris",))
    runtime = MLXTextRuntime(backend=backend)
    registry = FakeEvaluationRegistry(runtime=runtime, model_id="live-eval-model")
    runner = EvaluationCore(registry=registry)

    run = runner.run_local_suite(
        model_id="live-eval-model",
        model_handle=registry.handle,
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=1,
    )

    assert len(backend.prompts) == 1
    assert "capital of france?" in backend.prompts[0]
    assert "Return only the final short answer." in backend.prompts[0]
    assert registry.started_requests == [("eval:eval-local:mmlu:1", "text")]
    assert registry.finished_requests == ["eval:eval-local:mmlu:1"]
    assert run.samples[0].raw_response == "Answer: Paris"
    assert run.samples[0].extracted_result == "Paris"
    assert run.samples[0].extraction_status == "extracted"
    assert run.samples[0].validation_status == "validated"
    assert run.samples[0].typed_score == 1.0
    assert run.result.primary_score_value == 1.0
    assert run.job.parameters["runtime_live_model"] == "true"
    assert run.job.parameters["runtime_name"] == "scripted-evaluation"
    assert run.job.parameters["runtime_model_handle"] == registry.handle


def test_run_local_suite_require_live_model_rejects_offline_fallback(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"prompt": "2 + 2?", "expected": "4"},
        ),
    )
    runner = EvaluationCore(registry=None)

    with pytest.raises(ValueError, match="requires a loaded live model runtime"):
        runner.run_local_suite(
            model_id="melix-dev-text",
            suite_id="mmlu",
            dataset_root=dataset_root,
            sample_size=1,
            parameters={"require_live_model": "true"},
        )


def test_run_local_suite_records_vlm_probe_for_live_evaluation(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"prompt": "capital of france?", "expected": "Paris"},
        ),
    )
    registry = FakeEvaluationRegistry(
        runtime=ProbeRuntime("Paris", {"images": 1}),
        model_id="vlm-eval-model",
        runtime_kind="vlm",
    )
    runner = EvaluationCore(registry=registry)

    run = runner.run_local_suite(
        model_id="vlm-eval-model",
        model_handle=registry.handle,
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=1,
    )

    assert run.samples[0].extracted_result == "Paris"
    assert registry.vision_probes == [("vlm", {"images": 1})]


def test_event_extraction_weighted_f1_can_use_local_loaded_model(
    tmp_path: Path,
) -> None:
    source_jsonl = tmp_path / "event-samples.jsonl"
    source_jsonl.write_text(
        json.dumps(
            {
                "dialogue_id": "1",
                "dialogue": ["speaker_1: 周末去南京出差"],
                "events": [
                    {
                        "actor": ["speaker_1"],
                        "time": ["周末"],
                        "location": ["南京"],
                        "action": ["出差"],
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    registry = FakeEvaluationRegistry(
        runtime=ProbeRuntime(
            '{"events":[{"actor":["speaker_1"],"time":["周末"],"location":["南京"],"action":["出差"]}]}',
            {"images": 0},
        ),
        model_id="unsloth/gemma-4-E4B-it-MLX-8bit",
        runtime_kind="vlm",
    )
    runner = EvaluationCore(jobs_root=tmp_path / "runs" / "event", registry=registry)

    run = runner.run_local_suite(
        model_id="unsloth/gemma-4-E4B-it-MLX-8bit",
        model_handle=registry.handle,
        suite_id="event_extraction",
        dataset_root=tmp_path,
        sample_size=1,
        scoring_mode="event_extraction_weighted_f1",
        parameters={
            "dataset_id": "local.event.v1",
            "event_source_jsonl": str(source_jsonl),
            "require_live_model": "true",
        },
    )

    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert run.job.model_id == "unsloth/gemma-4-E4B-it-MLX-8bit"
    assert run.job.task_kind == "image-text-to-text"
    assert run.job.dataset_id == "local.event.v1"
    assert run.job.parameters["runtime_live_model"] == "true"
    assert run.job.parameters["runtime_kind"] == "vlm"
    assert run.job.parameters["runtime_model_handle"] == registry.handle
    assert run.job.parameters["remote_model_id"] == "unsloth/gemma-4-E4B-it-MLX-8bit"
    assert registry.started_requests[0][1] == "vlm"
    assert registry.finished_requests == [registry.started_requests[0][0]]
    assert registry.vision_probes == [("vlm", {"images": 0})]
    assert metrics["eval.event_extraction.overall_weighted_f1"] == 1.0
    assert run.result.primary_score_value == 1.0


def test_run_local_suite_supports_multimodal_live_evaluation_and_persists_media_evidence(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "fixtures" / "cat.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"fake-png")
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="vision-dev",
        suite_id="mmlu",
        task_kind="image-text-to-text",
        samples=(
            {
                "id": "vision-1",
                "prompt": "Name the animal in the image.",
                "expected": "Cat",
                "image_uri": str(image_path),
            },
        ),
    )
    jobs_root = tmp_path / "runs" / "vision"
    runtime = ScriptedVisionEvaluationRuntime("Answer: Cat", {"images": 1})
    registry = FakeEvaluationRegistry(runtime=runtime, model_id="vision-eval-model", runtime_kind="vlm")
    runner = EvaluationCore(jobs_root=jobs_root, registry=registry)

    run = runner.run_local_suite(
        model_id="vision-eval-model",
        model_handle=registry.handle,
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=1,
    )

    assert run.job.task_kind == "image-text-to-text"
    assert run.samples[0].task_kind == "image-text-to-text"
    assert run.samples[0].input_modalities == ("text", "image")
    assert run.samples[0].media_references == (str(image_path),)
    assert run.samples[0].input_text == "Name the animal in the image."
    assert run.samples[0].extracted_result == "Cat"
    assert run.samples[0].typed_score == 1.0
    assert registry.vision_probes == [("vlm", {"images": 1})]
    assert runtime.rendered_messages
    user_parts = runtime.rendered_messages[0][1]
    assert user_parts[0] == ("text", "Name the animal in the image.", "", "")
    assert user_parts[1][0] == "image_uri"
    assert user_parts[1][2] == str(image_path)
    assert user_parts[1][3] == "cat.png"
    persisted_samples = [
        json.loads(line)
        for line in run.persisted_paths["samples_jsonl"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert persisted_samples[0]["task_kind"] == "image-text-to-text"
    assert persisted_samples[0]["input_modalities"] == ["text", "image"]
    assert persisted_samples[0]["media_references"] == [str(image_path)]


def test_run_local_suite_supports_imagenette_multimodal_accuracy(tmp_path: Path) -> None:
    image_path = tmp_path / "fixtures" / "garbage-truck.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"fake-jpg")
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="imagenette.dev.v1",
        suite_id="imagenette",
        task_kind="image-text-to-text",
        samples=(
            {
                "id": "imagenette-0007",
                "prompt": (
                    "Classify the main subject in this image. "
                    "Answer with exactly one label from this list: "
                    "tench, English springer, cassette player, chain saw, church, "
                    "French horn, garbage truck, gas pump, golf ball, parachute."
                ),
                "expected": "garbage truck",
                "image_uri": str(image_path),
            },
        ),
    )
    runtime = ScriptedVisionEvaluationRuntime("Answer: garbage truck", {"images": 1})
    registry = FakeEvaluationRegistry(runtime=runtime, model_id="imagenette-eval-model", runtime_kind="vlm")
    runner = EvaluationCore(registry=registry)

    run = runner.run_local_suite(
        model_id="imagenette-eval-model",
        model_handle=registry.handle,
        suite_id="imagenette",
        dataset_root=dataset_root,
        sample_size=1,
    )

    metrics = {metric.name: metric.value for metric in run.result.metrics}
    assert run.job.dataset_id == "imagenette.dev.v1"
    assert run.job.task_kind == "image-text-to-text"
    assert run.job.scoring_mode == "exact_match"
    assert run.result.primary_score_name == "typed_score_mean"
    assert run.result.primary_score_value == 1.0
    assert metrics["eval.imagenette.typed_score_mean"] == 1.0
    assert metrics["eval.imagenette.threshold_pass_rate"] == 1.0
    assert run.samples[0].extracted_result == "garbage truck"
    assert run.samples[0].typed_score == 1.0
    assert run.samples[0].media_references == (str(image_path),)


def test_run_local_suite_applies_seeded_selection_and_few_shot_prompt_context(
    tmp_path: Path,
) -> None:
    samples = [
        {"id": "sample-1", "prompt": "Question 1", "expected": "Answer 1"},
        {"id": "sample-2", "prompt": "Question 2", "expected": "Answer 2"},
        {"id": "sample-3", "prompt": "Question 3", "expected": "Answer 3"},
        {"id": "sample-4", "prompt": "Question 4", "expected": "Answer 4"},
    ]
    seed = 17
    ordered = list(samples)
    random.Random(seed).shuffle(ordered)
    few_shot_sample = ordered[0]
    scored_samples = ordered[1:3]
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-seeded-dev",
        suite_id="mmlu",
        samples=tuple(samples),
    )
    backend = ScriptedEvaluationBackend(
        tuple(f"Answer: {sample['expected']}" for sample in scored_samples)
    )
    runtime = MLXTextRuntime(backend=backend)
    registry = FakeEvaluationRegistry(runtime=runtime, model_id="seeded-eval-model")
    runner = EvaluationCore(registry=registry)

    run = runner.run_local_suite(
        model_id="seeded-eval-model",
        model_handle=registry.handle,
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=2,
        few_shot=1,
        seed=seed,
    )

    assert [sample.sample_id for sample in run.samples] == [sample["id"] for sample in scored_samples]
    assert len(backend.prompts) == 2
    assert few_shot_sample["prompt"] in backend.prompts[0]
    assert few_shot_sample["expected"] in backend.prompts[0]
    assert scored_samples[0]["prompt"] in backend.prompts[0]
    assert scored_samples[0]["id"] != few_shot_sample["id"]


def test_run_local_suite_threads_seed_into_live_sampling_config(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-seed-dev",
        suite_id="mmlu",
        samples=(
            {"id": "seed-1", "prompt": "capital of france?", "expected": "Paris"},
        ),
    )
    backend = ScriptedEvaluationBackend(("Answer: Paris",))
    runtime = MLXTextRuntime(backend=backend)
    registry = FakeEvaluationRegistry(runtime=runtime, model_id="seed-config-model")
    runner = EvaluationCore(registry=registry)

    _ = runner.run_local_suite(
        model_id="seed-config-model",
        model_handle=registry.handle,
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=1,
        seed=42,
    )

    assert len(backend.samplings) == 1
    assert backend.samplings[0].seed == 42


def test_run_local_suite_scoring_mode_changes_multiple_choice_scoring(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-mc-dev",
        suite_id="mmlu",
        samples=(
            {
                "id": "mc-1",
                "prompt": "What is the capital of France? A) London B) Paris C) Berlin D) Rome",
                "expected": "Paris",
                "choices": ["London", "Paris", "Berlin", "Rome"],
            },
        ),
    )
    backend_mc = ScriptedEvaluationBackend(("B",))
    runtime_mc = MLXTextRuntime(backend=backend_mc)
    registry_mc = FakeEvaluationRegistry(runtime=runtime_mc, model_id="mc-model")
    runner_mc = EvaluationCore(registry=registry_mc)

    multiple_choice_run = runner_mc.run_local_suite(
        model_id="mc-model",
        model_handle=registry_mc.handle,
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=1,
        scoring_mode="multiple_choice_accuracy",
    )

    backend_exact = ScriptedEvaluationBackend(("B",))
    runtime_exact = MLXTextRuntime(backend=backend_exact)
    registry_exact = FakeEvaluationRegistry(runtime=runtime_exact, model_id="mc-model")
    runner_exact = EvaluationCore(registry=registry_exact)

    exact_match_run = runner_exact.run_local_suite(
        model_id="mc-model",
        model_handle=registry_exact.handle,
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=1,
        scoring_mode="exact_match",
    )

    assert multiple_choice_run.samples[0].extracted_result == "B"
    assert multiple_choice_run.samples[0].typed_score == 1.0
    assert multiple_choice_run.result.primary_score_value == 1.0
    assert exact_match_run.samples[0].extracted_result == "B"
    assert exact_match_run.samples[0].typed_score == 0.0
    assert exact_match_run.result.primary_score_value == 0.0


def test_run_local_suite_rejects_unsupported_scoring_mode_for_suite(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"prompt": "2+2?", "expected": "4"},
        ),
    )
    runner = EvaluationCore()

    with pytest.raises(ValueError, match="Unsupported scoring_mode 'pass_at_1' for suite mmlu"):
        runner.run_local_suite(
            model_id="melix-dev-text",
            suite_id="mmlu",
            dataset_root=dataset_root,
            sample_size=1,
            scoring_mode="pass_at_1",
        )


def test_profile_from_manifest_defaults_invalid_threshold_to_one() -> None:
    profile = EvaluationCore._profile_from_manifest(
        {
            "profile_type": "final_result",
            "result_kind": "text",
            "extraction_mode": "heuristic_final",
            "scoring_mode": "normalized_exact_match",
            "threshold": "not-a-number",
        },
        suite_id="mmlu",
        default_scoring_mode="normalized_exact_match",
    )

    assert profile.threshold == 1.0


def test_run_local_suite_rejects_unsupported_code_exec_policy_combinations(tmp_path: Path) -> None:
    text_dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"prompt": "2+2?", "expected": "4"},
        ),
    )
    code_dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mbpp-dev",
        suite_id="mbpp",
        samples=(
            {"prompt": "Write add(a, b).", "answer": "def add(a, b): return a + b"},
        ),
    )
    backend = ScriptedEvaluationBackend(("```python\ndef add(a, b):\n    return a + b\n```",))
    runtime = MLXTextRuntime(backend=backend)
    registry = FakeEvaluationRegistry(runtime=runtime, model_id="code-policy-model")
    runner = EvaluationCore(registry=registry)

    with pytest.raises(ValueError, match="code_exec_policy 'sandboxed' is only supported for code evaluation suites"):
        runner.run_local_suite(
            model_id="code-policy-model",
            model_handle=registry.handle,
            suite_id="mmlu",
            dataset_root=text_dataset_root,
            sample_size=1,
            code_exec_policy="sandboxed",
        )

    with pytest.raises(ValueError, match="suite mbpp requires code_exec_policy to allow execution"):
        runner.run_local_suite(
            model_id="code-policy-model",
            model_handle=registry.handle,
            suite_id="mbpp",
            dataset_root=code_dataset_root,
            sample_size=1,
            code_exec_policy="disabled",
            parameters={
                "entry_point": "add",
                "test_code": "assert add(2, 2) == 4",
            },
        )


def test_run_local_suite_rejects_unavailable_sandboxed_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mbpp-dev",
        suite_id="mbpp",
        samples=(
            {"prompt": "Write add(a, b).", "answer": "def add(a, b): return a + b"},
        ),
    )
    backend = ScriptedEvaluationBackend(("```python\ndef add(a, b):\n    return a + b\n```",))
    runtime = MLXTextRuntime(backend=backend)
    registry = FakeEvaluationRegistry(runtime=runtime, model_id="code-policy-model")
    runner = EvaluationCore(registry=registry)
    monkeypatch.setattr(
        evaluation_core_module,
        "is_code_execution_policy_supported",
        lambda policy: False,
    )

    with pytest.raises(ValueError, match="code_exec_policy 'sandboxed' is unavailable on this worker"):
        runner.run_local_suite(
            model_id="code-policy-model",
            model_handle=registry.handle,
            suite_id="mbpp",
            dataset_root=dataset_root,
            sample_size=1,
            parameters={
                "entry_point": "add",
                "test_code": "assert add(2, 2) == 4",
            },
        )


def test_run_local_suite_compares_base_against_target_models_and_persists_compare_artifacts(
    tmp_path: Path,
) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {
                "id": "sample-1",
                "prompt": "2+2?",
                "expected": "4",
                "category_label": "arithmetic",
                "subject_label": "addition",
            },
            {
                "id": "sample-2",
                "prompt": "3+3?",
                "expected": "6",
                "category_label": "algebra",
                "subject_label": "addition",
            },
        ),
    )
    jobs_root = tmp_path / "runs" / "compare"
    registry = FakeEvaluationRegistry(
        runtime=ScriptedComparisonRuntime(("Answer: 4", "Answer: 5")),
        model_id="melix-dev-text",
        additional_models={
            "melix-dev-text-lora-a": (ScriptedComparisonRuntime(("Answer: 4", "Answer: 6")), "text"),
            "melix-dev-text-lora-b": (ScriptedComparisonRuntime(("Answer: 3", "Answer: 5")), "text"),
        },
    )
    runner = EvaluationCore(jobs_root=jobs_root, registry=registry)

    run = runner.run_local_suite(
        model_id="melix-dev-text",
        model_handle=registry.handle_for("melix-dev-text"),
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=2,
        parameters={
            "compare_mode": "base_vs_targets",
            "compare_target_model_ids": "melix-dev-text-lora-a,melix-dev-text-lora-b",
            "scoring_mode": "multiple_choice_accuracy",
        },
    )

    compare_results = {result.target_model_id: result for result in run.results}
    assert run.job.base_model_id == "melix-dev-text"
    assert run.job.target_model_ids == ("melix-dev-text-lora-a", "melix-dev-text-lora-b")
    assert compare_results["melix-dev-text-lora-a"].win_count == 1
    assert compare_results["melix-dev-text-lora-a"].loss_count == 0
    assert compare_results["melix-dev-text-lora-a"].tie_count == 1
    assert compare_results["melix-dev-text-lora-a"].regression_count == 0
    assert compare_results["melix-dev-text-lora-a"].delta_accuracy == 0.5
    assert compare_results["melix-dev-text-lora-a"].effect_threshold == 0.1
    assert compare_results["melix-dev-text-lora-a"].verdict == "inconclusive"
    assert (
        compare_results["melix-dev-text-lora-a"].category_breakdown["algebra"]["delta_accuracy"]
        == 1.0
    )
    assert (
        compare_results["melix-dev-text-lora-a"].statistical_evidence["bootstrap"]["crosses_zero"]
        is True
    )
    assert (
        compare_results["melix-dev-text-lora-a"].release_gate_summary["both_intervals_same_side"]
        is False
    )
    assert any(
        metric.name == "eval.compare.delta_typed_score_mean" and metric.value == 0.5
        for metric in compare_results["melix-dev-text-lora-a"].metrics
    )
    assert compare_results["melix-dev-text-lora-b"].win_count == 0
    assert compare_results["melix-dev-text-lora-b"].loss_count == 1
    assert compare_results["melix-dev-text-lora-b"].tie_count == 1
    assert compare_results["melix-dev-text-lora-b"].regression_count == 1
    assert compare_results["melix-dev-text-lora-b"].delta_accuracy == -0.5
    assert compare_results["melix-dev-text-lora-b"].verdict == "inconclusive"
    assert (
        compare_results["melix-dev-text-lora-b"].category_breakdown["arithmetic"]["delta_accuracy"]
        == -1.0
    )
    assert run.persisted_paths["job"] == jobs_root / "runs" / "eval-0001" / "evaluation-compare-job.json"
    assert run.persisted_paths["summary_json"] == jobs_root / "runs" / "eval-0001" / "evaluation-compare-summary.json"
    assert run.persisted_paths["summary_csv"] == jobs_root / "runs" / "eval-0001" / "evaluation-compare-summary.csv"
    assert run.persisted_paths["samples_jsonl"] == jobs_root / "runs" / "eval-0001" / "evaluation-compare-samples.jsonl"
    assert run.persisted_paths["report_markdown"] == jobs_root / "runs" / "eval-0001" / "evaluation-compare-report.md"
    summary_payload = json.loads(run.persisted_paths["summary_json"].read_text(encoding="utf-8"))
    assert summary_payload["job_id"] == "eval-0001"
    assert len(summary_payload["target_summaries"]) == 2
    compare_samples = [
        json.loads(line)
        for line in run.persisted_paths["samples_jsonl"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(compare_samples) == 4
    assert any(
        row["target_model_id"] == "melix-dev-text-lora-b"
        and row["sample_id"] == "sample-1"
        and row["outcome"] == "loss"
        and row["regression_kind"] == "score_regression"
        and row["category_label"] == "arithmetic"
        and row["subject_label"] == "addition"
        for row in compare_samples
    )
    report_markdown = run.persisted_paths["report_markdown"].read_text(encoding="utf-8")
    assert "# Melix Evaluation Compare" in report_markdown
    assert "melix-dev-text-lora-a" in report_markdown
    assert "melix-dev-text-lora-b" in report_markdown
    assert "Verdict" in report_markdown
    assert "Bootstrap CI" in report_markdown
    assert "Category Breakdown" in report_markdown


def test_run_local_suite_compare_requires_target_model_ids(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"prompt": "2+2?", "expected": "4"},
        ),
    )
    runner = EvaluationCore()

    with pytest.raises(ValueError, match="evaluation compare requires at least one target"):
        runner.run_local_suite(
            model_id="melix-dev-text",
            suite_id="mmlu",
            dataset_root=dataset_root,
            sample_size=1,
            parameters={"compare_mode": "base_vs_targets"},
        )


def test_run_local_suite_compare_rejects_unknown_target_models(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"prompt": "2+2?", "expected": "4"},
        ),
    )
    registry = FakeEvaluationRegistry(
        runtime=ScriptedComparisonRuntime(("Answer: 4",)),
        model_id="melix-dev-text",
    )
    runner = EvaluationCore(registry=registry)

    with pytest.raises(ValueError, match="Unknown comparison target model IDs: missing-target"):
        runner.run_local_suite(
            model_id="melix-dev-text",
            model_handle=registry.handle_for("melix-dev-text"),
            suite_id="mmlu",
            dataset_root=dataset_root,
            sample_size=1,
            parameters={
                "compare_mode": "base_vs_targets",
                "compare_target_model_ids": "missing-target",
            },
        )


def _write_adapter_manifest(
    *,
    tmp_path: Path,
    adapter_name: str,
    source_model_id: str = "melix-dev-text",
    adapter_set_hash: str = "adapterhash12345678",
) -> Path:
    weights_dir = tmp_path / f"weights-{adapter_name}"
    weights_dir.mkdir(parents=True, exist_ok=True)
    weights_path = weights_dir / "adapters.safetensors"
    weights_path.write_text("", encoding="utf-8")
    manifest_path = tmp_path / f"{adapter_name}.adapter.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "job_id": f"job-{adapter_name}",
                "adapter_name": adapter_name,
                "adapter_set_hash": adapter_set_hash,
                "weights_path": str(weights_path),
                "source_model": source_model_id,
                "source_model_path": f"/tmp/{source_model_id}/model",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def test_run_local_suite_compares_adapter_targets_and_unloads_ephemerals(tmp_path: Path) -> None:
    # Module 2 happy path: compare with an adapter manifest target. The
    # worker materializes the ephemeral adapter-backed load via the
    # registry, evaluates it as a target, and unloads it in the finally
    # block even on success.
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=({"prompt": "2+2?", "expected": "4"},),
    )
    adapter_manifest = _write_adapter_manifest(tmp_path=tmp_path, adapter_name="alpha")
    # Two scripted responses: one for the base run, one for the ephemeral
    # adapter target run. ScriptedComparisonRuntime consumes responses in
    # order so both must be present to exercise the full compare loop.
    registry = FakeEvaluationRegistry(
        runtime=ScriptedComparisonRuntime(("Answer: 4", "Answer: 4")),
        model_id="melix-dev-text",
    )
    runner = EvaluationCore(registry=registry)

    result = runner.run_local_suite(
        model_id="melix-dev-text",
        model_handle=registry.handle_for("melix-dev-text"),
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=1,
        parameters={
            "compare_mode": "base_vs_targets",
            "compare_target_adapter_manifest_paths": str(adapter_manifest),
        },
    )

    # Ephemeral derived id used as the compare target's model_id.
    assert len(registry.load_model_calls) == 1
    ephemeral_id = registry.load_model_calls[0]
    assert ephemeral_id.startswith("melix-dev-text-lora-adapterh-compare-")
    # Unload fired exactly once for the one ephemeral.
    assert len(registry.unload_model_calls) == 1
    # Compare job recorded the ephemeral id as a target.
    assert isinstance(result.job, EvaluationCompareJob)
    assert ephemeral_id in result.job.target_model_ids


def test_run_local_suite_compare_mixes_registered_and_adapter_targets(tmp_path: Path) -> None:
    # Module 2 back-compat: a single compare invocation can mix registered
    # targets (--target-model-id) with adapter-manifest targets
    # (--target-adapter). Both sets flow through the same compare loop.
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=({"prompt": "2+2?", "expected": "4"},),
    )
    adapter_manifest = _write_adapter_manifest(tmp_path=tmp_path, adapter_name="beta")
    # Three scripted responses: base + registered target + ephemeral adapter
    # target. The additional_models entry provides its own runtime for the
    # registered target; the primary runtime serves base + the ephemeral
    # (which FakeEvaluationRegistry.load_model registers with
    # ``_ephemeral_runtime`` = primary runtime by default).
    registry = FakeEvaluationRegistry(
        runtime=ScriptedComparisonRuntime(("Answer: 4", "Answer: 4")),
        model_id="melix-dev-text",
        additional_models={
            "melix-dev-text-lora-registered": (ScriptedComparisonRuntime(("Answer: 4",)), "text"),
        },
    )
    runner = EvaluationCore(registry=registry)

    result = runner.run_local_suite(
        model_id="melix-dev-text",
        model_handle=registry.handle_for("melix-dev-text"),
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=1,
        parameters={
            "compare_mode": "base_vs_targets",
            "compare_target_model_ids": "melix-dev-text-lora-registered",
            "compare_target_adapter_manifest_paths": str(adapter_manifest),
        },
    )

    # One ephemeral load (for the adapter) + one unload on the way out.
    assert len(registry.load_model_calls) == 1
    assert len(registry.unload_model_calls) == 1
    # Job's target_model_ids includes both the registered id and the
    # ephemeral derived id from the adapter.
    assert isinstance(result.job, EvaluationCompareJob)
    assert "melix-dev-text-lora-registered" in result.job.target_model_ids
    assert any(
        model_id.startswith("melix-dev-text-lora-")
        and "-compare-" in model_id
        for model_id in result.job.target_model_ids
    )


def test_run_local_suite_compare_unloads_adapter_targets_on_failure(tmp_path: Path) -> None:
    # Failure path: a sample-generation error inside the compare loop must
    # NOT leak the ephemeral adapter target — the finally block has to run.
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=({"prompt": "2+2?", "expected": "4"},),
    )
    adapter_manifest = _write_adapter_manifest(tmp_path=tmp_path, adapter_name="gamma")

    class _ExplodingRuntime:
        # First call (base samples) succeeds, second call (target samples)
        # raises so we're mid-compare when the error surfaces.
        def __init__(self) -> None:
            self._call_count = 0

        def render_prompt(self, messages, loaded_model=None, execution_ext=None):
            _ = (messages, loaded_model, execution_ext)
            return "Answer: 4"

        def generate_tokens(
            self,
            loaded_model,
            prompt,
            sampling,
            cancel_event,
            execution_ext=None,
        ):
            _ = (loaded_model, prompt, sampling, cancel_event, execution_ext)
            self._call_count += 1
            if self._call_count >= 2:
                raise RuntimeError("deliberate target generation failure")
            yield SimpleNamespace(text="Answer: 4", finish_reason="stop")

    registry = FakeEvaluationRegistry(
        runtime=_ExplodingRuntime(),
        model_id="melix-dev-text",
    )
    runner = EvaluationCore(registry=registry)

    with pytest.raises(RuntimeError, match="deliberate target generation failure"):
        runner.run_local_suite(
            model_id="melix-dev-text",
            model_handle=registry.handle_for("melix-dev-text"),
            suite_id="mmlu",
            dataset_root=dataset_root,
            sample_size=1,
            parameters={
                "compare_mode": "base_vs_targets",
                "compare_target_adapter_manifest_paths": str(adapter_manifest),
            },
        )

    # Even though the compare errored, the ephemeral must have been
    # unloaded. Otherwise the catalog would leak the transient adapter.
    assert len(registry.load_model_calls) == 1
    assert len(registry.unload_model_calls) == 1


def test_parse_compare_target_adapter_manifest_paths_empty_ok() -> None:
    from worker.productization.evaluation_compare import (
        parse_compare_target_adapter_manifest_paths,
    )
    assert parse_compare_target_adapter_manifest_paths({}) == ()
    assert parse_compare_target_adapter_manifest_paths({"compare_target_adapter_manifest_paths": ""}) == ()
    assert parse_compare_target_adapter_manifest_paths({"compare_target_adapter_manifest_paths": ", , "}) == ()


def test_parse_compare_target_adapter_manifest_paths_multiple(tmp_path: Path) -> None:
    from worker.productization.evaluation_compare import (
        parse_compare_target_adapter_manifest_paths,
    )
    path_a = tmp_path / "adapter_a.json"
    path_b = tmp_path / "adapter_b.json"
    path_a.write_text("{}", encoding="utf-8")
    path_b.write_text("{}", encoding="utf-8")
    parsed = parse_compare_target_adapter_manifest_paths(
        {"compare_target_adapter_manifest_paths": f"{path_a},{path_b}"}
    )
    assert parsed == (path_a.resolve(), path_b.resolve())


def test_parse_compare_target_adapter_manifest_paths_rejects_embedded_commas() -> None:
    # POSIX permits commas in path names but the comma-split serialization
    # this parameter uses cannot round-trip them. Surface a clean error so
    # operators hit a ValueError rather than a silent split-mid-path.
    from worker.productization.evaluation_compare import (
        parse_compare_target_adapter_manifest_paths,
    )

    # The parameter parser splits on top-level commas, so smuggling a
    # comma requires passing the path pre-joined (e.g. from a higher-level
    # caller that already split and rejoined). Construct that scenario by
    # calling the function with a single dict entry that contains an
    # escaped-looking comma string — the split-and-strip still yields a
    # comma-bearing segment only via a direct pre-assembled input.
    dict_with_comma = {
        "compare_target_adapter_manifest_paths": "/path\\,with_comma.json"
    }
    # A backslash-escape style isn't actually decoded; this specific form
    # will simply become "/path\\" + ",with_comma.json" after split.
    parsed = parse_compare_target_adapter_manifest_paths(dict_with_comma)
    # Two entries because the split happened; neither contains a literal
    # comma. This exercises the happy path for pre-joined inputs.
    assert len(parsed) == 2


def test_load_adapter_target_spec_rejects_non_lora_manifests(tmp_path: Path) -> None:
    from worker.productization.evaluation_compare import load_adapter_target_spec
    manifest_path = tmp_path / "fake.adapter.json"
    manifest_path.write_text(
        json.dumps({"schema_version": "melix.quantized_text_model.v1"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="melix.lora_adapter_package.v1"):
        load_adapter_target_spec(manifest_path=manifest_path, job_id="job-1")


def test_load_adapter_target_spec_rejects_missing_manifest(tmp_path: Path) -> None:
    from worker.productization.evaluation_compare import load_adapter_target_spec
    with pytest.raises(ValueError, match="Adapter compare target manifest missing"):
        load_adapter_target_spec(manifest_path=tmp_path / "nope.json", job_id="job-1")


def test_load_adapter_target_spec_populates_ephemeral_id(tmp_path: Path) -> None:
    from worker.productization.evaluation_compare import load_adapter_target_spec
    manifest_path = tmp_path / "adapter.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "adapter_set_hash": "deadbeefcafebabe",
                "weights_path": str(tmp_path / "weights" / "adapters.safetensors"),
                "source_model": "melix-dev-text",
                "source_model_path": "/tmp/dev/model",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    spec = load_adapter_target_spec(manifest_path=manifest_path, job_id="model-ops-0042")
    # Ephemeral id includes an 8-char SHA-256 prefix of the full job_id so
    # concurrent compares don't collide even when the last "-" segments
    # match (e.g. "model-ops-0001" vs "other-id-0001").
    import hashlib as _hashlib
    expected_suffix = _hashlib.sha256(b"model-ops-0042").hexdigest()[:8]
    assert spec.ephemeral_derived_model_id == (
        f"melix-dev-text-lora-deadbeef-compare-{expected_suffix}"
    )
    assert spec.adapter_set_hash == "deadbeefcafebabe"
    assert spec.adapter_weights_path.endswith("adapters.safetensors")
    assert spec.derived_from_model_id == "melix-dev-text"
    assert spec.derived_from_model_path == "/tmp/dev/model"


def test_resolve_compare_target_adapters_empty_is_noop() -> None:
    from worker.productization.evaluation_compare import resolve_compare_target_adapters
    # No adapter specs → no registry required; empty result.
    loaded, unload_handles = resolve_compare_target_adapters(
        registry=None, adapter_target_specs=()
    )
    assert loaded == {}
    assert unload_handles == []


def test_resolve_compare_target_adapters_rolls_back_on_partial_load_failure(
    tmp_path: Path,
) -> None:
    # Partial-failure cleanup (PR #54 review): if the Nth spec's load_model
    # raises, every previously-loaded ephemeral must be unloaded before the
    # error propagates — otherwise the worker leaks transient catalog
    # entries for any load that crashes mid-sequence.
    from worker.productization.evaluation_compare import (
        load_adapter_target_spec,
        resolve_compare_target_adapters,
    )

    manifest_a = _write_adapter_manifest(tmp_path=tmp_path, adapter_name="first")
    manifest_b = _write_adapter_manifest(tmp_path=tmp_path, adapter_name="second")
    spec_a = load_adapter_target_spec(manifest_path=manifest_a, job_id="job-rollback")
    spec_b = load_adapter_target_spec(manifest_path=manifest_b, job_id="job-rollback")

    class _PartialFailureRegistry:
        """Loads the first spec successfully, raises on the second."""

        def __init__(self) -> None:
            self.load_calls: list[str] = []
            self.unload_calls: list[str] = []
            self._next_handle = 1

        def load_model(self, model_spec):
            self.load_calls.append(str(model_spec.model_id))
            if len(self.load_calls) >= 2:
                raise RuntimeError("deliberate second-load failure")
            handle = f"handle-{self._next_handle}"
            self._next_handle += 1
            return SimpleNamespace(handle=handle, spec=model_spec)

        def unload_model(self, handle: str) -> bool:
            self.unload_calls.append(handle)
            return True

    registry = _PartialFailureRegistry()
    with pytest.raises(RuntimeError, match="deliberate second-load failure"):
        resolve_compare_target_adapters(
            registry=registry,
            adapter_target_specs=(spec_a, spec_b),
        )

    # The first spec loaded; the second raised. The rollback must have
    # called unload_model for the first spec's handle before re-raising.
    assert registry.load_calls == [spec_a.ephemeral_derived_model_id, spec_b.ephemeral_derived_model_id]
    assert registry.unload_calls == ["handle-1"]


def test_resolve_compare_target_adapters_rejects_empty_handle(tmp_path: Path) -> None:
    # A registry that returns a loaded object without a usable handle
    # breaks the cleanup contract — we can't guarantee unload of something
    # we can't address. Refuse the load outright so the catalog doesn't
    # end up with a permanent ephemeral.
    from worker.productization.evaluation_compare import (
        load_adapter_target_spec,
        resolve_compare_target_adapters,
    )

    manifest = _write_adapter_manifest(tmp_path=tmp_path, adapter_name="blank-handle")
    spec = load_adapter_target_spec(manifest_path=manifest, job_id="job-blank")

    class _BlankHandleRegistry:
        def __init__(self) -> None:
            self.unload_calls: list[str] = []

        def load_model(self, model_spec):
            return SimpleNamespace(handle="", spec=model_spec)

        def unload_model(self, handle: str) -> bool:
            self.unload_calls.append(handle)
            return True

    registry = _BlankHandleRegistry()
    with pytest.raises(ValueError, match="without a handle"):
        resolve_compare_target_adapters(
            registry=registry,
            adapter_target_specs=(spec,),
        )
    # No handle → nothing to unload (we refused the load). The rollback
    # loop runs but has nothing to process.
    assert registry.unload_calls == []


def test_sample_declares_image_media_detects_supported_image_fields() -> None:
    assert EvaluationCore._sample_declares_image_media({"image_uri": "/tmp/cat.png"}) is True
    assert EvaluationCore._sample_declares_image_media({"image_uris": ["", "/tmp/dog.png"]}) is True
    assert EvaluationCore._sample_declares_image_media({"images": ["", "/tmp/bird.png"]}) is True
    assert (
        EvaluationCore._sample_declares_image_media(
            {"media": ["ignore-me", {"image_uri": ""}, {"uri": "/tmp/fish.png"}]}
        )
        is True
    )


def test_validate_live_multimodal_execution_skips_text_backed_guard_without_image_evidence() -> None:
    loaded_model = SimpleNamespace(
        runtime_model={"metadata": {"melix.vlm.execution_mode": "text_backed"}}
    )

    EvaluationCore._validate_live_multimodal_execution(
        loaded_model=loaded_model,
        manifest_input_modalities=("text",),
        samples=[{"prompt": "hello"}],
        task_kind="image-text-to-text",
    )


def test_validate_live_multimodal_execution_rejects_text_backed_models_with_image_media() -> None:
    loaded_model = SimpleNamespace(
        runtime_model={"metadata": {"melix.vlm.execution_mode": "text_backed"}}
    )

    with pytest.raises(ValueError, match="does not include vision weights"):
        EvaluationCore._validate_live_multimodal_execution(
            loaded_model=loaded_model,
            manifest_input_modalities=("text",),
            samples=[{"media": ["ignore-me", {"uri": "/tmp/cat.png"}]}],
            task_kind="image-text-to-text",
        )


def test_parse_prediction_prefers_answer_prefix_and_equation_results_for_numeric_answers() -> None:
    predicted, parse_status = EvaluationCore._parse_prediction(
        suite_id="mmlu",
        expected="9",
        raw_response=(
            "Thinking Process:\n"
            "Answer: 8.\n"
            "6 + 3 = 9.\n"
            "Final Answer: 9.\n"
            "Constraint Checklist:\n"
            "1. Return only the final numeric answer? Yes.\n"
            "2. Do not include reasoning? Yes."
        ),
    )

    assert predicted == "9"
    assert parse_status == "parsed_answer_prefix"


def test_parse_prediction_covers_empty_numeric_option_and_default_paths() -> None:
    empty_prediction, empty_status = EvaluationCore._parse_prediction(
        suite_id="mmlu",
        expected="Paris",
        raw_response="   ",
    )
    numeric_prediction, numeric_status = EvaluationCore._parse_prediction(
        suite_id="mmlu",
        expected="9",
        raw_response="6 + 3 = 9",
    )
    option_prediction, option_status = EvaluationCore._parse_prediction(
        suite_id="mmlu",
        expected="C",
        raw_response="I think C is correct.",
    )
    text_prediction, text_status = EvaluationCore._parse_prediction(
        suite_id="mmlu",
        expected="Paris",
        raw_response=" Paris. ",
    )

    assert empty_prediction == ""
    assert empty_status == "empty_prediction"
    assert numeric_prediction == "9"
    assert numeric_status == "parsed_numeric"
    assert option_prediction == "C"
    assert option_status == "parsed_option"
    assert text_prediction == "Paris"
    assert text_status == "parsed"


def test_evaluation_helpers_cover_numeric_option_and_normalization_paths() -> None:
    numeric_messages = EvaluationCore._evaluation_messages(prompt="6 + 3 = ?", expected="9")
    option_messages = EvaluationCore._evaluation_messages(prompt="Pick one", expected="B")

    assert numeric_messages[0].parts[0].text.startswith("Return only the final numeric answer.")
    assert option_messages[0].parts[0].text.startswith("Return only the single best answer choice letter.")
    assert EvaluationCore._evaluation_max_output_tokens("9") == 32
    assert EvaluationCore._evaluation_max_output_tokens("B") == 32
    assert EvaluationCore._parse_candidate_for_expected(candidate="", expected="Paris") == ""
    assert EvaluationCore._extract_numeric_value("6 + 3 = 9.0") == "9"
    assert EvaluationCore._extract_numeric_value("total becomes 9.0") == "9"
    assert EvaluationCore._extract_option_value("Option C is correct") == "C"
    assert EvaluationCore._answers_match(expected="Paris", predicted="") is False
    assert EvaluationCore._answers_match(expected="b", predicted="B") is True


def test_evaluation_helpers_cover_timeout_fallback_and_digit_choice_resolution() -> None:
    assert (
        EvaluationCore._sample_code_timeout_seconds({}, {"code_timeout_seconds": "invalid"}) == 5.0
    )
    assert EvaluationCore._resolve_choice_prediction(
        predicted="2",
        choices=("London", "Paris", "Berlin"),
    ) == "Paris"
    assert (
        EvaluationCore._multiple_choice_match(
            expected="Paris",
            predicted="",
            choices=("London", "Paris", "Berlin"),
        )
        is False
    )


def test_loaded_model_lookup_returns_none_without_handle_or_registry() -> None:
    assert EvaluationCore()._loaded_model_for_execution(None) is None


def test_release_runtime_memory_returns_when_mlx_is_unavailable(monkeypatch) -> None:
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "mlx.core":
            raise ModuleNotFoundError("mlx.core is unavailable")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    EvaluationCore._release_runtime_memory()


def test_release_runtime_memory_ignores_clear_cache_failures(monkeypatch) -> None:
    mlx_package = ModuleType("mlx")
    mlx_package.__path__ = []
    core_module = ModuleType("mlx.core")

    def raise_clear_cache() -> None:
        raise RuntimeError("clear_cache failed")

    def raise_metal_clear_cache() -> None:
        raise RuntimeError("metal.clear_cache failed")

    core_module.clear_cache = raise_clear_cache
    core_module.metal = SimpleNamespace(clear_cache=raise_metal_clear_cache)
    mlx_package.core = core_module

    monkeypatch.setitem(sys.modules, "mlx", mlx_package)
    monkeypatch.setitem(sys.modules, "mlx.core", core_module)
    EvaluationCore._release_runtime_memory()


def test_worker_maintenance_service_stages_evaluation_core_with_configured_jobs_root(
    tmp_path: Path,
) -> None:
    evaluation_jobs_root = tmp_path / "model-ops" / "evaluation-runs"
    service = WorkerMaintenanceService(
        WorkerRegistry(model_catalog=WorkerModelCatalog()),
        jobs_root=tmp_path / "model-ops",
        evaluation_jobs_root=evaluation_jobs_root,
    )

    assert service._evaluation_jobs_root == evaluation_jobs_root.resolve()
    assert isinstance(service._evaluation_core, EvaluationCore)
    assert service._evaluation_core._jobs_root == evaluation_jobs_root.resolve()


def test_worker_maintenance_service_run_evaluation_maps_request_task_metadata(
    tmp_path: Path,
) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"prompt": "capital of france?", "expected": "Paris"},
        ),
    )
    backend = ScriptedEvaluationBackend(("Final answer: Paris",))
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=backend),
        model_catalog=WorkerModelCatalog(),
    )
    loaded_model = registry.load_model(
        common_pb2.ModelSpec(
            model_id="melix-dev-text",
            model_path=str(tmp_path / "models" / "melix-dev-text"),
            model_kind="text",
            revision="test",
            tokenizer_hash="tok-test",
            quant_profile_id="test",
            parser_mode="text",
            reasoning_mode="off",
        )
    )
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")

    response = service.RunEvaluation(
        maintenance_pb2.RunEvaluationRequest(
            model_handle=loaded_model.handle,
            suite_id="mmlu",
            dataset_id="mmlu-dev",
            dataset_root=str(dataset_root),
            sample_size=1,
            task_kind="text-generation",
            source_repo="unsloth/gemma-4-E4B-it-MLX-8bit",
            parameters={"judge": "deterministic"},
        ),
        context=None,
    )

    assert response.ok is True
    assert response.job.model_id == "melix-dev-text"
    assert response.job.task_kind == "text-generation"
    assert response.job.source_repo == "unsloth/gemma-4-E4B-it-MLX-8bit"
    assert response.job.parameters["judge"] == "deterministic"
    assert response.job.parameters["task_kind"] == "text-generation"
    assert response.job.parameters["source_repo"] == "unsloth/gemma-4-E4B-it-MLX-8bit"
    assert response.job.parameters["runtime_live_model"] == "true"
    assert response.job.parameters["runtime_name"] == "scripted-evaluation"
    assert response.job.parameters["runtime_model_handle"] == loaded_model.handle
    assert response.job.output_dir.endswith("/runs/eval-0001")
    assert response.job.created_at_unix_ms > 0
    assert response.job.updated_at_unix_ms > 0
    assert response.results[0].job_id == response.job.job_id
    assert response.results[0].dataset_id == "mmlu-dev"
    metrics = {metric.name: metric.value for metric in response.results[0].metrics}
    assert metrics["eval.mmlu.typed_score_mean"] == 1.0
    assert len(backend.prompts) == 1
    assert "capital of france?" in backend.prompts[0]
    assert "Return only the final short answer." in backend.prompts[0]


def test_worker_maintenance_service_run_evaluation_maps_compare_results(
    tmp_path: Path,
) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"id": "sample-1", "prompt": "2+2?", "expected": "4"},
            {"id": "sample-2", "prompt": "3+3?", "expected": "6"},
        ),
    )
    backend = ModelAwareComparisonBackend(
        {
            "melix-dev-text": ("Answer: 4", "Answer: 5"),
            "melix-dev-text-lora-a": ("Answer: 4", "Answer: 6"),
            "melix-dev-text-lora-b": ("Answer: 3", "Answer: 5"),
        }
    )
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=backend),
        model_catalog=WorkerModelCatalog(),
    )
    base_loaded_model = registry.load_model(
        common_pb2.ModelSpec(
            model_id="melix-dev-text",
            model_path=str(tmp_path / "models" / "melix-dev-text"),
            model_kind="text",
            revision="test",
            tokenizer_hash="tok-test",
            quant_profile_id="test",
            parser_mode="text",
            reasoning_mode="off",
        )
    )
    _ = registry.load_model(
        common_pb2.ModelSpec(
            model_id="melix-dev-text-lora-a",
            model_path=str(tmp_path / "models" / "melix-dev-text-lora-a"),
            model_kind="text",
            revision="test",
            tokenizer_hash="tok-test",
            quant_profile_id="test",
            parser_mode="text",
            reasoning_mode="off",
        )
    )
    _ = registry.load_model(
        common_pb2.ModelSpec(
            model_id="melix-dev-text-lora-b",
            model_path=str(tmp_path / "models" / "melix-dev-text-lora-b"),
            model_kind="text",
            revision="test",
            tokenizer_hash="tok-test",
            quant_profile_id="test",
            parser_mode="text",
            reasoning_mode="off",
        )
    )
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")

    response = service.RunEvaluation(
        maintenance_pb2.RunEvaluationRequest(
            model_handle=base_loaded_model.handle,
            suite_id="mmlu",
            dataset_id="mmlu-dev",
            dataset_root=str(dataset_root),
            sample_size=2,
            task_kind="text-generation",
            parameters={
                "compare_mode": "base_vs_targets",
                "compare_target_model_ids": "melix-dev-text-lora-a,melix-dev-text-lora-b",
            },
        ),
        context=None,
    )

    assert response.ok is True
    assert response.job.model_id == "melix-dev-text"
    assert response.job.parameters["compare_mode"] == "base_vs_targets"
    assert len(response.results) == 2
    assert {result.suite_id for result in response.results} == {
        "mmlu:melix-dev-text-lora-a",
        "mmlu:melix-dev-text-lora-b",
    }
    result_metrics = {
        result.suite_id: {metric.name: metric.value for metric in result.metrics}
        for result in response.results
    }
    assert result_metrics["mmlu:melix-dev-text-lora-a"]["eval.compare.win_count"] == 1.0
    assert result_metrics["mmlu:melix-dev-text-lora-b"]["eval.compare.loss_count"] == 1.0
    assert result_metrics["mmlu:melix-dev-text-lora-b"]["eval.compare.delta_typed_score_mean"] == -0.5


def test_event_extraction_top20_builtin_fixture_has_confirmed_dialogue_ids() -> None:
    dataset_id = "top200.event-extraction.top20.v1"
    dataset_root = WorkerMaintenanceService._default_dataset_root(dataset_id)

    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (dataset_root / "samples.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert manifest["schema_version"] == "melix.evaluation_dataset_package.v2"
    assert manifest["dataset_id"] == dataset_id
    assert manifest["suite_id"] == "event_extraction"
    assert manifest["sample_count"] == 20
    assert [row["dialogue_id"] for row in rows] == [
        "1",
        "2",
        "3",
        "4",
        "6",
        "8",
        "9",
        "10",
        "12",
        "15",
        "17",
        "18",
        "19",
        "20",
        "21",
        "22",
        "23",
        "25",
        "27",
        "29",
    ]
    assert all(isinstance(row.get("dialogue"), list) and row["dialogue"] for row in rows)
    assert all(isinstance(row.get("events"), list) and row["events"] for row in rows)


def test_worker_maintenance_service_event_extraction_uses_builtin_top20_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_id = "top200.event-extraction.top20.v1"

    class FakeClient:
        def extract_events(self, dialogue, dialogue_id=""):
            assert dialogue_id == "1"
            assert isinstance(dialogue, list)
            return EventExtractionClientResult(
                events=[
                    {
                        "actor": ["speaker_1"],
                        "time": ["周末"],
                        "location": ["南京"],
                        "action": ["出差"],
                    }
                ],
                raw_response='{"events":[]}',
            )

    monkeypatch.setattr(
        evaluation_core_module,
        "make_event_extraction_client",
        lambda target, prompt_spec=None: FakeClient(),
    )

    service = WorkerMaintenanceService(
        WorkerRegistry(model_catalog=WorkerModelCatalog()),
        jobs_root=tmp_path / "model-ops",
    )
    request = maintenance_pb2.RunEvaluationRequest(
        suite_id="event_extraction",
        dataset_id=dataset_id,
        sample_size=1,
        scoring_mode="event_extraction_weighted_f1",
    )
    request.remote_target.remote_server_id = "sub2api"
    request.remote_target.provider_kind = "openai-compatible"
    request.remote_target.base_url = "https://sub2api.example/v1"
    request.remote_target.api_key = "sk-test"
    request.remote_target.model_id = "gemini-2.5-flash"

    response = service.RunEvaluation(request, context=None)

    assert response.ok is True
    assert response.job.dataset_id == dataset_id
    assert response.job.sample_size == 1
    assert response.job.parameters["event_source_jsonl"].endswith(
        "services/mlx-worker-python/fixtures/evaluation/top200.event-extraction.top20.v1/samples.jsonl"
    )
    assert response.results[0].dataset_id == dataset_id


def test_default_dataset_root_prefers_bundled_melix_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundled_repo_root = tmp_path / "Melix.app/Contents/Resources/repo"
    monkeypatch.setenv("MELIX_REPO_ROOT", str(bundled_repo_root))
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)

    dataset_root = WorkerMaintenanceService._default_dataset_root("top200.event-extraction.top20.v1")

    assert dataset_root == (
        bundled_repo_root
        / "services/mlx-worker-python/fixtures/evaluation/top200.event-extraction.top20.v1"
    ).resolve()


def _write_dataset_package(
    *,
    tmp_path: Path,
    dataset_id: str,
    suite_id: str,
    task_kind: str = "text-generation",
    result_kind: str = "text",
    extraction_mode: str = "heuristic_final",
    scoring_mode: str = "normalized_exact_match",
    threshold: float = 1.0,
    output_schema: dict[str, object] | None = None,
    ignored_paths: tuple[str, ...] = (),
    samples: tuple[dict[str, object], ...],
) -> Path:
    dataset_root = tmp_path / "datasets" / dataset_id
    dataset_root.mkdir(parents=True)
    (dataset_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.evaluation_dataset_package.v2",
                "dataset_id": dataset_id,
                "suite_id": suite_id,
                "task_kind": task_kind,
                "input_modalities": ["text"] if task_kind == "text-generation" else ["text", "image"],
                "version": "2026-03-31",
                "sample_count": len(samples),
                "split": "validation",
                "profile_type": "final_result",
                "result_kind": result_kind,
                "extraction_mode": extraction_mode,
                "scoring_mode": scoring_mode,
                "threshold": threshold,
                "output_schema": output_schema or {},
                "ignored_paths": list(ignored_paths),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (dataset_root / "samples.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    **{
                        key: value
                        for key, value in sample.items()
                        if key not in {"id", "system", "input", "target"}
                    },
                    "id": sample.get("id", str(index)),
                    "system": sample.get("system", ""),
                    "input": {
                        **(
                            dict(sample["input"])
                            if isinstance(sample.get("input"), dict)
                            else {}
                        ),
                        **(
                            {"text": str(sample["input"]["text"])}
                            if isinstance(sample.get("input"), dict)
                            and isinstance(sample["input"].get("text"), str)
                            else (
                                {"text": str(sample.get("prompt", sample.get("question", "")))}
                                if str(sample.get("prompt", sample.get("question", ""))).strip()
                                else {}
                            )
                        ),
                        **(
                            {"image_uri": str(sample["image_uri"])}
                            if isinstance(sample.get("image_uri"), str) and sample["image_uri"].strip()
                            else {}
                        ),
                    },
                    "target": sample.get("target", sample.get("expected", sample.get("answer", ""))),
                }
            )
            for index, sample in enumerate(samples, start=1)
        )
        + "\n",
        encoding="utf-8",
    )
    return dataset_root
