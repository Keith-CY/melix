from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from packages.protocol.python.worker.v1 import maintenance_pb2
from worker.engine.evaluation_core import EvaluationCore
from worker.grpc_server import WorkerMaintenanceService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.productization import topic_membership_runner as topic_runner_module
from worker.productization.evaluation_schemas import EvaluationCompareJob
from worker.registry import WorkerRegistry
from worker.runtime.mlx_text_runtime import RuntimeTokenEvent
from worker.productization.topic_membership import (
    SEMANTIC_JUDGE_PROMPT_HASH,
    SEMANTIC_SCORING_MODE,
    STRICT_SCORING_MODE,
    TopicMembershipClientResult,
    evaluate_topic_membership,
    required_ids,
    score_dataset,
)



class FakeEvaluationRegistry:
    def __init__(
        self,
        *,
        runtime,
        model_id: str = "melix-dev-text",
        runtime_kind: str = "text",
        ephemeral_runtime: object | None = None,
    ) -> None:
        self._primary_model_id = model_id
        self._loaded_models_by_handle: dict[str, object] = {}
        self._handles_by_model_id: dict[str, str] = {}
        self._register_loaded_model(model_id=model_id, runtime=runtime, runtime_kind=runtime_kind)
        self.started_requests: list[tuple[str, str]] = []
        self.finished_requests: list[str] = []
        self.vision_probes: list[tuple[str, object]] = []
        self.load_model_calls: list[str] = []
        self.unload_model_calls: list[str] = []
        self._ephemeral_runtime = ephemeral_runtime or runtime

    @property
    def handle(self) -> str:
        return self._handles_by_model_id[self._primary_model_id]

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
        self.load_model_calls.append(str(model_spec.model_id))
        self._register_loaded_model(
            model_id=str(model_spec.model_id),
            runtime=self._ephemeral_runtime,
            runtime_kind="text",
        )
        return self._loaded_models_by_handle[self._handles_by_model_id[str(model_spec.model_id)]]

    def unload_model(self, handle: str) -> bool:
        self.unload_model_calls.append(handle)
        loaded = self._loaded_models_by_handle.pop(handle, None)
        if loaded is None:
            return False
        self._handles_by_model_id.pop(loaded.spec.model_id, None)
        return True


class ProbeRuntime:
    runtime_name = "probe-live-runtime"

    def __init__(self, response: str, probe: object) -> None:
        self._response = response
        self._probe = probe
        self.rendered_prompts: list[str] = []

    def render_prompt(self, messages, loaded_model=None, execution_ext=None, template_kwargs=None):
        _ = loaded_model
        _ = execution_ext
        _ = template_kwargs
        prompt = "\n".join(part.text for message in messages for part in message.parts)
        self.rendered_prompts.append(prompt)
        return prompt

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

def test_strict_topic_membership_uses_message_jaccard_threshold_exclusively() -> None:
    gold_cases = [
        {
            "source_dialogue_id": "dlg-1",
            "messages": [],
            "gold_topics": [
                {"gold_topic_id": "gold-match", "label": "A", "required_message_ids": ["m1", "m2"]},
                {"gold_topic_id": "gold-boundary", "label": "B", "required_message_ids": ["g0"]},
            ],
        }
    ]
    predictions = [
        {
            "source_dialogue_id": "dlg-1",
            "output_json": {
                "gold_topics": [
                    {
                        "topic_id": "pred-match",
                        "label": "unrelated label is ignored",
                        "required_message_ids": ["m2", "p1"],
                    },
                    {
                        "topic_id": "pred-boundary",
                        "label": "same label does not matter",
                        "required_message_ids": ["g0", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9"],
                    },
                ]
            },
        }
    ]

    result = score_dataset(gold_cases, predictions, scoring_mode=STRICT_SCORING_MODE)

    assert result["strict_membership"]["true_positive"] == 1
    assert result["strict_membership"]["false_positive"] == 11
    assert result["strict_membership"]["false_negative"] == 2
    assert result["per_case"][0]["matches"] == 1


def test_topic_membership_missing_and_parse_errors_fail_closed() -> None:
    gold_cases = [
        {
            "source_dialogue_id": "parse-error",
            "messages": [],
            "gold_topics": [{"required_message_ids": ["m1", "m2"]}],
        },
        {
            "source_dialogue_id": "missing",
            "messages": [],
            "gold_topics": [{"required_message_ids": ["m3"]}],
        },
    ]
    predictions = [{"source_dialogue_id": "parse-error", "output": "not json"}]

    result = score_dataset(gold_cases, predictions, scoring_mode=STRICT_SCORING_MODE)

    assert result["cases"] == 2
    assert result["missing_predictions"] == 1
    assert result["json_valid_rate"] == 0.0
    assert result["strict_membership"]["true_positive"] == 0
    assert result["strict_membership"]["false_positive"] == 0
    assert result["strict_membership"]["false_negative"] == 3
    assert [row["parse_status"] for row in result["per_case"]] == ["parse_error", "missing_prediction"]


def test_required_ids_treats_scalar_message_id_as_one_id() -> None:
    assert required_ids({"required_message_ids": "m12"}) == {"m12"}
    assert required_ids({"required_message_ids": 12}) == {"12"}


class _FakeTopicJudge:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def judge_topic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
        self.requests.append(request)
        return {
            "equivalent": True,
            "confidence": 0.9,
            "reason_code": "same_topic",
            "short_reason": "same plan topic",
        }


def test_semantic_topic_membership_uses_judge_for_topic_alignment_only() -> None:
    gold_cases = [
        {
            "source_dialogue_id": "dlg-semantic",
            "messages": [
                {"message_id": "m1", "sender": "speaker_1", "text": "Book the train ticket"},
                {"message_id": "m2", "sender": "speaker_2", "text": "Confirm the train ticket"},
            ],
            "gold_topics": [
                {
                    "gold_topic_id": "gold-train",
                    "label": "train ticket",
                    "description": "booking train ticket",
                    "required_message_ids": ["m1"],
                }
            ],
        }
    ]
    predictions = [
        {
            "source_dialogue_id": "dlg-semantic",
            "output_json": {
                "gold_topics": [
                    {
                        "topic_id": "pred-train",
                        "label": "train ticket booking",
                        "description": "confirm train ticket",
                        "required_message_ids": ["m2"],
                    }
                ]
            },
        }
    ]
    judge = _FakeTopicJudge()

    result = score_dataset(
        gold_cases,
        predictions,
        scoring_mode=SEMANTIC_SCORING_MODE,
        judge=judge,
        judge_remote_server_id="judge",
        judge_model_id="judge-model",
    )

    assert result["strict_membership"]["f1"] == 0.0
    assert result["semantic_membership"]["true_positive"] == 0
    assert result["semantic_membership"]["false_positive"] == 1
    assert result["semantic_membership"]["false_negative"] == 1
    assert result["semantic_membership"]["f1"] == 0.0
    assert result["per_case"][0]["semantic_matches"] == 1
    assert result["semantic_judge"]["calls"] == 1
    assert result["semantic_judge"]["judge_prompt_hash"] == SEMANTIC_JUDGE_PROMPT_HASH
    assert len(judge.requests) == 1


def test_semantic_topic_membership_requires_judge() -> None:
    with pytest.raises(ValueError, match="requires a semantic judge"):
        score_dataset([], [], scoring_mode=SEMANTIC_SCORING_MODE)


def test_evaluate_topic_membership_writes_semantic_judge_audit(tmp_path: Path) -> None:
    gold_path = tmp_path / "gold.jsonl"
    pred_path = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "summary.json"
    details_path = tmp_path / "details.jsonl"
    row_audit_path = tmp_path / "row-audit.jsonl"
    judge_audit_path = tmp_path / "judge-audit.jsonl"
    gold_path.write_text(
        json.dumps(
            {
                "source_dialogue_id": "dlg-audit",
                "messages": [{"message_id": "m1", "text": "train ticket"}],
                "gold_topics": [
                    {
                        "label": "train ticket",
                        "description": "train ticket",
                        "required_message_ids": ["m1"],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pred_path.write_text(
        json.dumps(
            {
                "source_dialogue_id": "dlg-audit",
                "output_json": {
                    "gold_topics": [
                        {
                            "label": "train ticket booking",
                            "description": "train ticket",
                            "required_message_ids": ["m2"],
                        }
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    summary = evaluate_topic_membership(
        gold_jsonl=gold_path,
        pred_jsonl=pred_path,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
        judge_audit_output=judge_audit_path,
        scoring_mode=SEMANTIC_SCORING_MODE,
        judge=_FakeTopicJudge(),
        judge_remote_server_id="judge",
        judge_model_id="judge-model",
    )

    audit_rows = [
        json.loads(line)
        for line in judge_audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert summary["semantic_judge"]["calls"] == 1
    assert len(audit_rows) == 1
    assert audit_rows[0]["status"] == "ok"
    assert audit_rows[0]["equivalent"] is True

def _write_topic_membership_source(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "source_dialogue_id": "dlg-topic-1",
                "messages": [
                    {"message_id": "m1", "sender": "speaker_1", "timestamp": "", "text": "Buy train tickets"},
                    {"message_id": "m2", "sender": "speaker_2", "timestamp": "", "text": "Confirm train tickets"},
                    {"message_id": "m3", "sender": "speaker_1", "timestamp": "", "text": "Talk about dinner"},
                ],
                "gold_topics": [
                    {
                        "gold_topic_id": "topic-train",
                        "label": "train tickets",
                        "description": "ticket planning",
                        "required_message_ids": ["m1", "m2"],
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def test_topic_membership_strict_micro_f1_can_use_local_loaded_model(tmp_path: Path) -> None:
    source_jsonl = tmp_path / "topic-samples.jsonl"
    _write_topic_membership_source(source_jsonl)
    registry = FakeEvaluationRegistry(
        runtime=ProbeRuntime(
            '{"gold_topics":[{"topic_id":"pred-train","label":"train tickets","required_message_ids":["m1","m2"]}]}',
            {"images": 0},
        ),
        model_id="melix-dev-text",
    )
    runner = EvaluationCore(jobs_root=tmp_path / "runs" / "topic", registry=registry)

    run = runner.run_local_suite(
        model_id="melix-dev-text",
        model_handle=registry.handle,
        suite_id="topic_membership",
        dataset_root=tmp_path,
        sample_size=1,
        scoring_mode="topic_membership_strict_micro_f1",
        parameters={
            "dataset_id": "local.topic.v1",
            "topic_membership_source_jsonl": str(source_jsonl),
            "eval_prompt_system_prompt": "Return topic membership JSON.",
            "require_live_model": "true",
        },
    )

    metrics = {metric.name: metric.value for metric in run.result.metrics}
    prompt_snapshot = json.loads(Path(run.job.parameters["prompt_snapshot"]).read_text(encoding="utf-8"))

    assert run.job.model_id == "melix-dev-text"
    assert run.job.task_kind == "text-generation"
    assert run.job.dataset_id == "local.topic.v1"
    assert run.job.parameters["runtime_live_model"] == "true"
    assert run.job.parameters["runtime_model_handle"] == registry.handle
    assert run.job.parameters["topic_membership_source_jsonl"] == str(source_jsonl.resolve())
    assert "eval_prompt_system_prompt" not in run.job.parameters
    assert prompt_snapshot["task_kind"] == "topic_membership"
    assert prompt_snapshot["system_prompt"] == "Return topic membership JSON."
    assert registry.started_requests[0][1] == "text"
    assert registry.finished_requests == [registry.started_requests[0][0]]
    assert metrics["eval.topic_membership.strict_membership_f1"] == 1.0
    assert metrics["eval.topic_membership.json_valid_rate"] == 1.0
    assert run.result.primary_score_name == "strict_membership_f1"
    assert run.result.primary_score_value == 1.0
    assert run.samples[0].sample_id == "dlg-topic-1"
    assert run.samples[0].typed_score == 1.0
    assert run.samples[0].extraction_status == "extracted"
    assert "train tickets" in run.samples[0].target


def test_topic_membership_parse_errors_fail_closed_in_local_suite(tmp_path: Path) -> None:
    source_jsonl = tmp_path / "topic-samples.jsonl"
    _write_topic_membership_source(source_jsonl)
    registry = FakeEvaluationRegistry(
        runtime=ProbeRuntime("not json", {"images": 0}),
        model_id="melix-dev-text",
    )
    runner = EvaluationCore(jobs_root=tmp_path / "runs" / "topic", registry=registry)

    run = runner.run_local_suite(
        model_id="melix-dev-text",
        model_handle=registry.handle,
        suite_id="topic_membership",
        dataset_root=tmp_path,
        sample_size=1,
        scoring_mode="topic_membership_strict_micro_f1",
        parameters={
            "topic_membership_source_jsonl": str(source_jsonl),
            "eval_prompt_system_prompt": "Return topic membership JSON.",
        },
    )

    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert run.result.primary_score_value == 0.0
    assert run.result.failure_count == 1
    assert metrics["eval.topic_membership.strict_membership_f1"] == 0.0
    assert metrics["eval.topic_membership.json_valid_rate"] == 0.0
    assert run.samples[0].typed_score == 0.0
    assert run.samples[0].extraction_status == "parse_error"
    assert run.samples[0].parse_status == "parse_error"
    assert "not json" in run.samples[0].raw_response


def test_topic_membership_compare_uses_adapter_target_and_global_micro_f1(
    tmp_path: Path,
) -> None:
    source_jsonl = tmp_path / "topic-samples.jsonl"
    _write_topic_membership_source(source_jsonl)
    adapter_manifest = _write_adapter_manifest(
        tmp_path=tmp_path,
        adapter_name="topic-alpha",
        source_model_id="melix-dev-text",
    )
    registry = FakeEvaluationRegistry(
        runtime=ProbeRuntime('{"gold_topics":[]}', {"images": 0}),
        model_id="melix-dev-text",
        ephemeral_runtime=ProbeRuntime(
            '{"gold_topics":[{"topic_id":"pred-train","label":"train tickets","required_message_ids":["m1","m2"]}]}',
            {"images": 0},
        ),
    )
    runner = EvaluationCore(jobs_root=tmp_path / "runs" / "topic", registry=registry)

    run = runner.run_local_suite(
        model_id="melix-dev-text",
        model_handle=registry.handle,
        suite_id="topic_membership",
        dataset_root=tmp_path,
        sample_size=1,
        scoring_mode="topic_membership_strict_micro_f1",
        parameters={
            "dataset_id": "local.topic.v1",
            "topic_membership_source_jsonl": str(source_jsonl),
            "eval_prompt_system_prompt": "Return topic membership JSON.",
            "compare_mode": "base_vs_targets",
            "compare_target_adapter_manifest_paths": str(adapter_manifest),
        },
    )

    assert isinstance(run.job, EvaluationCompareJob)
    assert len(registry.load_model_calls) == 1
    assert len(registry.unload_model_calls) == 1
    ephemeral_id = registry.load_model_calls[0]
    assert run.results[0].target_model_id == ephemeral_id
    assert run.results[0].base_accuracy == 0.0
    assert run.results[0].target_accuracy == 1.0
    assert run.results[0].delta_accuracy == 1.0
    metrics = {metric.name: metric.value for metric in run.results[0].metrics}
    assert metrics["eval.compare.delta_topic_membership_primary_f1"] == 1.0
    assert metrics["eval.compare.delta_strict_membership_f1"] == 1.0
    assert run.job.dataset_lineage is not None
    assert run.job.dataset_lineage.source_path == str(source_jsonl.resolve())
    assert run.job.dataset_lineage.scoring_mode == "topic_membership_strict_micro_f1"
    assert run.samples[0].target_typed_score == 1.0
    assert run.samples[0].base_typed_score == 0.0


def test_topic_membership_semantic_mode_uses_dedicated_judge_and_keeps_strict_metric(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_jsonl = tmp_path / "topic-samples.jsonl"
    source_jsonl.write_text(
        json.dumps(
            {
                "source_dialogue_id": "dlg-topic-semantic",
                "messages": [
                    {
                        "message_id": f"m{index}",
                        "sender": "speaker_1" if index % 2 else "speaker_2",
                        "timestamp": "",
                        "text": f"Train ticket planning message {index}",
                    }
                    for index in range(1, 11)
                ],
                "gold_topics": [
                    {
                        "gold_topic_id": "topic-train",
                        "label": "train ticket planning",
                        "description": "all messages plan a train ticket",
                        "required_message_ids": [f"m{index}" for index in range(1, 11)],
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    class FakeTarget:
        provider_kind = "openai-compatible"
        base_url = "https://sub2api.example/v1"
        api_key = "sk-secret"
        model_id = "remote-topic-model"
        timeout_seconds = 30
        rate_limit_per_minute = 0

    class FakeTopicClient:
        def generate_membership(self, gold_case):
            _ = gold_case
            return TopicMembershipClientResult(
                output_json={
                    "gold_topics": [
                        {
                            "topic_id": "pred-train",
                            "label": "train ticket planning",
                            "description": "confirm train ticket planning",
                            "required_message_ids": ["m1"],
                        }
                    ]
                },
                raw_response='{"gold_topics":[{"topic_id":"pred-train","label":"train ticket planning","description":"confirm train ticket planning","required_message_ids":["m1"]}]}',
            )

    class FakeTopicJudge:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def judge_topic_equivalence(self, request):
            self.requests.append(request)
            return {
                "equivalent": True,
                "confidence": 0.9,
                "reason_code": "same_topic",
                "short_reason": "same topic",
            }

    fake_judge = FakeTopicJudge()
    monkeypatch.setattr(
        topic_runner_module,
        "make_topic_membership_client",
        lambda target, prompt_spec: FakeTopicClient(),
    )
    monkeypatch.setattr(
        topic_runner_module,
        "make_topic_membership_semantic_judge_client",
        lambda target: fake_judge,
    )
    runner = EvaluationCore(jobs_root=tmp_path / "evals")

    run = runner.run_local_suite(
        model_id="remote-topic-model",
        suite_id="topic_membership",
        dataset_root=tmp_path,
        sample_size=1,
        scoring_mode="topic_membership_semantic_micro_f1",
        parameters={
            "dataset_id": "local.topic.v1",
            "topic_membership_source_jsonl": str(source_jsonl),
            "eval_prompt_system_prompt": "Return topic membership JSON.",
            "semantic_judge_remote_server_id": "judge",
            "semantic_judge_provider_kind": "openai-compatible",
            "semantic_judge_base_url": "https://judge.example/v1",
            "semantic_judge_api_key": "sk-judge",
            "semantic_judge_model_id": "judge-model",
        },
        remote_target=FakeTarget(),
    )

    metrics = {metric.name: metric.value for metric in run.result.metrics}
    summary = json.loads(Path(run.job.parameters["topic_membership_summary"]).read_text(encoding="utf-8"))
    judge_audit_rows = [
        json.loads(line)
        for line in Path(run.job.parameters["topic_membership_judge_audit"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert run.result.primary_score_name == "semantic_membership_f1"
    assert metrics["eval.topic_membership.strict_membership_f1"] == 0.0
    assert metrics["eval.topic_membership.semantic_membership_f1"] == pytest.approx(0.181818, abs=1e-6)
    assert metrics["eval.topic_membership.semantic_judge_calls"] == 1.0
    assert run.samples[0].typed_score == 0.1818
    assert summary["semantic_judge"]["judge_remote_server_id"] == "judge"
    assert summary["semantic_judge"]["judge_model_id"] == "judge-model"
    assert len(fake_judge.requests) == 1
    assert len(judge_audit_rows) == 1
    assert "semantic_judge_api_key" not in run.job.parameters
    assert "semantic_judge_base_url" not in run.job.parameters


def test_worker_maintenance_service_topic_membership_requires_and_maps_source_jsonl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_jsonl = tmp_path / "topic-samples.jsonl"
    _write_topic_membership_source(source_jsonl)

    class FakeClient:
        def generate_membership(self, gold_case):
            assert gold_case["source_dialogue_id"] == "dlg-topic-1"
            return TopicMembershipClientResult(
                output_json={
                    "gold_topics": [
                        {
                            "topic_id": "pred-train",
                            "label": "train tickets",
                            "required_message_ids": ["m1", "m2"],
                        }
                    ]
                },
                raw_response='{"gold_topics":[{"topic_id":"pred-train","required_message_ids":["m1","m2"]}]}',
            )

    monkeypatch.setattr(
        topic_runner_module,
        "make_topic_membership_client",
        lambda target, prompt_spec: FakeClient(),
    )

    service = WorkerMaintenanceService(
        WorkerRegistry(model_catalog=WorkerModelCatalog()),
        jobs_root=tmp_path / "model-ops",
    )
    missing_source_request = maintenance_pb2.RunEvaluationRequest(
        suite_id="topic_membership",
        sample_size=1,
        scoring_mode="topic_membership_strict_micro_f1",
        parameters={"eval_prompt_system_prompt": "Return topic membership JSON."},
    )

    missing_source_response = service.RunEvaluation(missing_source_request, context=None)

    assert missing_source_response.ok is False
    assert "--source-jsonl" in missing_source_response.error.message

    request = maintenance_pb2.RunEvaluationRequest(
        suite_id="topic_membership",
        sample_size=1,
        scoring_mode="topic_membership_strict_micro_f1",
        parameters={"eval_prompt_system_prompt": "Return topic membership JSON."},
    )
    request.source.local_jsonl.path = str(source_jsonl)
    request.remote_target.remote_server_id = "sub2api"
    request.remote_target.provider_kind = "openai-compatible"
    request.remote_target.base_url = "https://sub2api.example/v1"
    request.remote_target.api_key = "sk-test"
    request.remote_target.model_id = "deepseek-v4-pro"

    response = service.RunEvaluation(request, context=None)

    assert response.ok is True
    assert response.job.dataset_id == "topic-membership"
    assert response.job.parameters["topic_membership_source_jsonl"] == str(source_jsonl.resolve())
    assert response.job.parameters["evaluation_source_kind"] == "jsonl"
    assert response.results[0].dataset_id == "topic-membership"
