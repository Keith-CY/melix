from __future__ import annotations

import builtins
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

from packages.protocol.python.worker.v1 import common_pb2, maintenance_pb2
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

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

    def estimate_resident_bytes(self, model_spec) -> int:
        _ = model_spec
        return 1024

    def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event):
        _ = loaded_model
        _ = sampling
        self.prompts.append(prompt)
        if cancel_event.is_set():
            return
        text = self._responses.pop(0)
        yield RuntimeTokenEvent(text=text, completion_tokens=max(1, len(text.split())))


class FakeEvaluationRegistry:
    def __init__(self, *, runtime, model_id: str = "melix-dev-text", runtime_kind: str = "text") -> None:
        self._runtime = runtime
        self._loaded_model = SimpleNamespace(
            handle=f"{model_id}::test",
            runtime_kind=runtime_kind,
            runtime_model={"model_id": model_id},
            spec=SimpleNamespace(model_id=model_id, ext={"melix.source_repo": "test/source"}),
            runtime=runtime,
        )
        self.started_requests: list[tuple[str, str]] = []
        self.finished_requests: list[str] = []
        self.vision_probes: list[tuple[str, object]] = []

    @property
    def handle(self) -> str:
        return self._loaded_model.handle

    def get_loaded_model(self, handle: str):
        if handle == self._loaded_model.handle:
            return self._loaded_model
        return None

    def runtime_for_loaded_model(self, loaded_model):
        _ = loaded_model
        return self._runtime

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
    runner = EvaluationCore(jobs_root=jobs_root)

    run = runner.run_local_suite(
        model_id="melix-dev-text",
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=2,
        few_shot=4,
        seed=7,
        scoring_mode="multiple_choice_accuracy",
        code_exec_policy="sandboxed",
    )

    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert run.job.dataset_id == "mmlu-dev"
    assert run.job.sample_size == 2
    assert run.job.task_kind == "text-generation"
    assert run.job.few_shot == 4
    assert run.job.seed == 7
    assert run.job.scoring_mode == "multiple_choice_accuracy"
    assert run.job.code_exec_policy == "sandboxed"
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


def test_run_local_suite_respects_sample_size_for_deterministic_accuracy(tmp_path: Path) -> None:
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
    assert metrics["eval.mmlu.accuracy"] == 0.5
    assert metrics["eval.mmlu.correct_count"] == 1.0
    assert run.persisted_paths == {}
    assert len(run.samples) == 2


def test_run_local_suite_supports_additional_score_modes_and_job_metadata(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mbpp-dev",
        suite_id="mbpp",
        samples=(
            {"id": "sample-1", "question": "2+2?", "answer": "4"},
        ),
    )
    jobs_root = tmp_path / "runs" / "mbpp"
    runner = EvaluationCore(jobs_root=jobs_root)

    run = runner.run_local_suite(
        model_id="melix-dev-text",
        suite_id="mbpp",
        dataset_root=dataset_root,
        sample_size=1,
        parameters={
            "task_kind": "text-generation",
            "source_repo": "openai_humaneval",
        },
    )

    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert run.job.job_id == "eval-0001"
    assert run.job.source_repo == "openai_humaneval"
    assert run.job.output_dir == str(jobs_root / "runs" / "eval-0001")
    assert run.job.scoring_mode == "pass_at_1"
    assert run.job.few_shot == 0
    assert run.job.seed == 0
    assert run.job.code_exec_policy == ""
    assert metrics["eval.mbpp.pass_at_1"] == 1.0


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
            "code_exec_policy": "sandboxed",
        },
    )

    assert run.job.few_shot == 0
    assert run.job.seed == 0
    assert run.job.code_exec_policy == "sandboxed"
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


def _write_dataset_package(
    *,
    tmp_path: Path,
    dataset_id: str,
    suite_id: str,
    samples: tuple[dict[str, str], ...],
) -> Path:
    dataset_root = tmp_path / "datasets" / dataset_id
    dataset_root.mkdir(parents=True)
    (dataset_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.evaluation_dataset_package.v1",
                "dataset_id": dataset_id,
                "suite_id": suite_id,
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
