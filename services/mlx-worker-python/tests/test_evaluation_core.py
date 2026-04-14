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


class FakeEvaluationRegistry:
    def __init__(
        self,
        *,
        runtime,
        model_id: str = "melix-dev-text",
        runtime_kind: str = "text",
        additional_models: dict[str, tuple[object, str]] | None = None,
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


class ProbeRuntime:
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
    assert metrics["eval.mmlu.accuracy"] == 1.0
    assert metrics["eval.mmlu.correct_count"] == 2.0
    assert metrics["eval.mmlu.incorrect_count"] == 0.0
    assert metrics["eval.mmlu.duration_seconds"] >= 0.0
    assert run.result.score_name == "accuracy"
    assert run.result.score_value == 1.0
    assert run.result.correct_count == 2
    assert run.result.incorrect_count == 0
    assert run.result.duration_seconds >= 0.0
    assert run.job.job_id == "eval-0001"
    assert run.persisted_paths["job"] == jobs_root / "runs" / "eval-0001" / "evaluation-job.json"
    assert run.persisted_paths["result"] == jobs_root / "runs" / "eval-0001" / "evaluation-result.json"
    assert run.persisted_paths["summary_json"] == jobs_root / "runs" / "eval-0001" / "evaluation-summary.json"
    assert run.persisted_paths["summary_csv"] == jobs_root / "runs" / "eval-0001" / "evaluation-summary.csv"
    assert run.persisted_paths["samples_jsonl"] == jobs_root / "runs" / "eval-0001" / "evaluation-samples.jsonl"
    assert json.loads(run.persisted_paths["job"].read_text(encoding="utf-8")) == run.job.to_dict()
    assert json.loads(run.persisted_paths["result"].read_text(encoding="utf-8")) == run.result.to_dict()
    assert json.loads(run.persisted_paths["summary_json"].read_text(encoding="utf-8"))["score_name"] == "accuracy"
    assert "job_id,task_kind,source_repo,model_id,suite_id,dataset_id,score_name,score_value,sample_size,correct_count,incorrect_count,duration_seconds,created_at_unix_ms" in run.persisted_paths["summary_csv"].read_text(encoding="utf-8")
    persisted_samples = [
        json.loads(line)
        for line in run.persisted_paths["samples_jsonl"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert persisted_samples == [sample.to_dict() for sample in run.samples]
    assert len(run.samples) == 2
    assert run.samples[0].sample_id == "1"
    assert run.samples[0].correct is True

    queue_payload = json.loads((jobs_root / "queue" / f"{run.job.job_id}.json").read_text(encoding="utf-8"))
    assert queue_payload["job_kind"] == "evaluation"
    assert queue_payload["status"] == "completed"
    assert queue_payload["parameters"]["sample_size"] == "2"
    assert queue_payload["started_at_unix_ms"] > 0
    assert queue_payload["completed_at_unix_ms"] > 0


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
    assert metrics["eval.mmlu.accuracy"] == 0.0
    assert metrics["eval.mmlu.correct_count"] == 0.0
    assert run.persisted_paths == {}
    assert len(run.samples) == 2
    assert run.samples[0].predicted == ""
    assert run.samples[0].correct is False
    assert run.samples[0].parse_status == "no_live_model"
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
    assert metrics["eval.mbpp.pass_at_1"] == 1.0
    assert metrics["eval.mbpp.code_exec_pass_count"] == 1.0
    assert metrics["eval.mbpp.code_exec_fail_count"] == 0.0
    assert run.samples[0].correct is True
    assert run.samples[0].code_language == "python"
    assert run.samples[0].code_entry_point == "add"
    assert run.samples[0].code_compile_status == "compiled"
    assert run.samples[0].code_runtime_status == "ok"
    assert run.samples[0].code_timeout_status == "ok"
    assert run.samples[0].code_test_status == "passed"
    assert run.samples[0].code_tests_passed == 2
    assert run.samples[0].code_tests_total == 2
    assert run.samples[0].code_failure_detail == ""
    assert "def add" in run.samples[0].predicted


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
    assert run.samples[0].correct is True
    assert run.samples[0].parse_status == "parsed_code_block"
    assert run.samples[0].code_language == "python"
    assert run.samples[0].code_entry_point == "identity"
    assert run.samples[0].code_test_status == "passed"
    assert run.result.score_name == "pass_at_1"
    assert run.result.score_value == 1.0
    assert metrics["eval.humaneval.pass_at_1"] == 1.0
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
    assert run.samples[0].predicted == "Paris"
    assert run.samples[0].parse_status == "parsed_answer_prefix"
    assert run.samples[0].correct is True
    assert run.result.score_value == 1.0


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

    assert run.samples[0].predicted == "Paris"
    assert registry.vision_probes == [("vlm", {"images": 1})]


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
    assert run.samples[0].predicted == "Cat"
    assert run.samples[0].correct is True
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
    assert run.result.score_name == "accuracy"
    assert run.result.score_value == 1.0
    assert metrics["eval.imagenette.accuracy"] == 1.0
    assert metrics["eval.imagenette.correct_count"] == 1.0
    assert metrics["eval.imagenette.incorrect_count"] == 0.0
    assert run.samples[0].predicted == "garbage truck"
    assert run.samples[0].correct is True
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

    assert multiple_choice_run.samples[0].predicted == "B"
    assert multiple_choice_run.samples[0].correct is True
    assert multiple_choice_run.result.score_value == 1.0
    assert exact_match_run.samples[0].predicted == "B"
    assert exact_match_run.samples[0].correct is False
    assert exact_match_run.result.score_value == 0.0


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
            {"id": "sample-1", "prompt": "2+2?", "expected": "4"},
            {"id": "sample-2", "prompt": "3+3?", "expected": "6"},
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
    assert compare_results["melix-dev-text-lora-b"].win_count == 0
    assert compare_results["melix-dev-text-lora-b"].loss_count == 1
    assert compare_results["melix-dev-text-lora-b"].tie_count == 1
    assert compare_results["melix-dev-text-lora-b"].regression_count == 1
    assert compare_results["melix-dev-text-lora-b"].delta_accuracy == -0.5
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
        and row["regression"] is True
        for row in compare_samples
    )
    report_markdown = run.persisted_paths["report_markdown"].read_text(encoding="utf-8")
    assert "# Melix Evaluation Compare" in report_markdown
    assert "melix-dev-text-lora-a" in report_markdown
    assert "melix-dev-text-lora-b" in report_markdown


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

    with pytest.raises(ValueError, match="compare_target_model_ids must include at least one target model ID"):
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
    assert response.job.output_dir.endswith("/runs/eval-0001")
    assert response.job.created_at_unix_ms > 0
    assert response.job.updated_at_unix_ms > 0
    assert response.results[0].job_id == response.job.job_id
    assert response.results[0].dataset_id == "mmlu-dev"
    metrics = {metric.name: metric.value for metric in response.results[0].metrics}
    assert metrics["eval.mmlu.accuracy"] == 1.0
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


def _write_dataset_package(
    *,
    tmp_path: Path,
    dataset_id: str,
    suite_id: str,
    task_kind: str = "text-generation",
    samples: tuple[dict[str, object], ...],
) -> Path:
    dataset_root = tmp_path / "datasets" / dataset_id
    dataset_root.mkdir(parents=True)
    (dataset_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.evaluation_dataset_package.v1",
                "dataset_id": dataset_id,
                "suite_id": suite_id,
                "task_kind": task_kind,
                "input_modalities": ["text"] if task_kind == "text-generation" else ["text", "image"],
                "version": "2026-03-31",
                "sample_count": len(samples),
                "split": "validation",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (dataset_root / "samples.jsonl").write_text(
        "\n".join(json.dumps(sample) for sample in samples) + "\n",
        encoding="utf-8",
    )
    return dataset_root
