from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.errors import ModelOperationError
from worker.model_ops import mlx_lm_runner as mlx_lm_runner_module
from worker.model_ops import training_config as training_config_module
from worker.runtime.mlx_text_runtime import MLXTextRuntime, RuntimeTokenEvent, RuntimeToolCallEvent


def _text_model(*, model_path: str = "models/plain-llama") -> common_pb2.ModelSpec:
    model = common_pb2.ModelSpec(
        model_id="melix-test-text",
        model_path=model_path,
        model_kind="text",
        revision="main",
        max_context=4096,
    )
    model.ext["text_layer_count"] = "2"
    return model


def test_mlx_lm_runner_runtime_grpo_executes_candidate_tool_trajectories(
    tmp_path: Path,
) -> None:
    class ToolCallingPolicyBackend:
        runtime_name = "tool-calling-policy-runtime"

        def load_model(self, model_spec):
            return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

        def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event, execution_ext=None):
            del loaded_model, sampling, cancel_event
            assert execution_ext["melix.tool_parser.mode"] == "qwen"
            assert "visit" in execution_ext["melix.tool_parser.namespaces"]
            if "candidate 1" in prompt:
                yield RuntimeToolCallEvent(
                    call_id="visit-selected",
                    tool_name="visit",
                    arguments_json_fragment=json.dumps({"url": "fixture://selected"}),
                )
                yield RuntimeTokenEvent(text="selected tool-backed answer")
            else:
                yield RuntimeToolCallEvent(
                    call_id="visit-extra",
                    tool_name="visit",
                    arguments_json_fragment=json.dumps({"url": "fixture://extra"}),
                )
                yield RuntimeToolCallEvent(
                    call_id="compute-extra",
                    tool_name="local_compute",
                    arguments_json_fragment=json.dumps({"code": "1 + 1"}),
                )
                yield RuntimeTokenEvent(text="extra tool answer")

    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={
            "training_mode": "grpo",
            "grpo_candidate_count": "2",
            "candidate_generation_mode": "runtime_generate",
            "candidate_generation_max_tokens": "16",
        },
        dataset_format="prompt_candidate",
        response_only_supported=False,
        sample_count=1,
    )
    normalized_dataset_dir = tmp_path / "normalized"
    normalized_dataset_dir.mkdir()
    (normalized_dataset_dir / "train.jsonl").write_text(
        json.dumps(
            {
                "prompt": "Use tools and answer.",
                "tool_budget": 1,
                "tool_fixture_context": {
                    "pages": {
                        "fixture://selected": {
                            "title": "Selected",
                            "text": "Selected source.",
                        },
                        "fixture://extra": {
                            "title": "Extra",
                            "text": "Extra source.",
                        },
                    }
                },
                "candidates": [
                    {"text": "selected tool-backed answer", "score": 1.0},
                    {"text": "extra tool answer", "score": 0.9},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-grpo-runtime-tools",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=normalized_dataset_dir,
        config=config,
        dataset_format="prompt_candidate",
    )

    result = mlx_lm_runner_module.MLXLMRunner(
        policy_runtime=MLXTextRuntime(backend=ToolCallingPolicyBackend())
    ).train(request)

    trace_rows = [
        json.loads(line)
        for line in Path(result.metrics.policy_update_trace_path).read_text(encoding="utf-8").splitlines()
    ]
    row = trace_rows[0]

    assert row["selected_candidate_index"] == 0
    assert row["selected_candidate_text"] == "selected tool-backed answer"
    assert row["candidate_reward_trace_schema_version"] == (
        "melix.alignment_candidate_reward_trace.v1"
    )
    assert row["candidate_reward_trace_count"] == 2
    assert row["candidate_reward_trace_total_count"] == 2
    assert result.metrics.candidate_reward_trace_count == 2
    assert result.metrics.candidate_reward_trace_schema_version == (
        "melix.alignment_candidate_reward_trace.v1"
    )
    assert row["selected_candidate_tool_call_count"] == 1
    assert row["agentic_tool_calls"][0]["id"] == "visit-selected"
    assert row["agentic_tool_observations"][0]["payload"]["text"] == "Selected source."
    assert row["agentic_tool_metrics"]["agentic_tool.call_count"] == 1.0
    assert row["reward_components"]["tool_efficiency"] == 0.0
    assert row["generated_candidates"][0]["tool_calls"][0]["name"] == "visit"
    assert row["generated_candidates"][0]["agentic_tool_observation_count"] == 1
    assert row["generated_candidates"][1]["tool_calls"][1]["name"] == "local_compute"
    assert row["generated_candidates"][1]["agentic_tool_metrics"]["agentic_tool.call_count"] == 2.0
    assert row["generated_candidates"][1]["reward_components"]["tool_efficiency"] == -1.0

    candidate_trace_rows = [
        json.loads(line)
        for line in Path(result.metrics.candidate_reward_trace_path).read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    adapter_config = json.loads(result.adapter_config_path.read_text(encoding="utf-8"))
    selected_trace = candidate_trace_rows[0]
    extra_trace = candidate_trace_rows[1]

    assert adapter_config["candidate_reward_trace_path"] == (
        result.metrics.candidate_reward_trace_path
    )
    assert adapter_config["candidate_reward_trace_count"] == 2
    assert adapter_config["candidate_reward_trace_schema_version"] == (
        "melix.alignment_candidate_reward_trace.v1"
    )
    assert row["candidate_reward_trace_path"] == result.metrics.candidate_reward_trace_path
    assert selected_trace["schema_version"] == "melix.alignment_candidate_reward_trace.v1"
    assert selected_trace["sample_index"] == 0
    assert selected_trace["candidate_index"] == 0
    assert selected_trace["selected"] is True
    assert selected_trace["candidate_text"] == "selected tool-backed answer"
    assert selected_trace["reward_components"] == row["reward_components"]
    assert selected_trace["agentic_tool_calls"][0]["id"] == "visit-selected"
    assert selected_trace["agentic_tool_observations"][0]["payload"]["text"] == "Selected source."
    assert selected_trace["agentic_tool_metrics"]["agentic_tool.call_count"] == 1.0
    assert len(selected_trace["replay_fingerprint"]) == 64
    assert extra_trace["candidate_index"] == 1
    assert extra_trace["selected"] is False
    assert extra_trace["tool_call_count"] == 2
    assert extra_trace["agentic_tool_observation_count"] == 2
    assert extra_trace["tool_calls"][1]["name"] == "local_compute"
    assert "agentic_tool_observations" not in extra_trace


def test_runtime_grpo_marks_tool_timeout_candidate_as_fatal_mask(
    tmp_path: Path,
) -> None:
    class TimeoutPolicyBackend:
        runtime_name = "timeout-policy-runtime"

        def load_model(self, model_spec):
            return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

        def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event, execution_ext=None):
            del loaded_model, sampling, cancel_event, execution_ext
            if "candidate 1" in prompt:
                yield RuntimeToolCallEvent(
                    call_id="timeout-visit",
                    tool_name="visit",
                    arguments_json_fragment=json.dumps({"url": "fixture://timeout"}),
                )
                yield RuntimeTokenEvent(text="fatal timeout answer")
            else:
                yield RuntimeTokenEvent(text="ordinary fallback response")

    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={
            "training_mode": "grpo",
            "grpo_candidate_count": "2",
            "candidate_generation_mode": "runtime_generate",
            "candidate_generation_max_tokens": "16",
        },
        dataset_format="prompt_candidate",
        response_only_supported=False,
        sample_count=1,
    )
    normalized_dataset_dir = tmp_path / "normalized"
    normalized_dataset_dir.mkdir()
    (normalized_dataset_dir / "train.jsonl").write_text(
        json.dumps(
            {
                "prompt": "Use tools and answer.",
                "tool_fixture_context": {
                    "tool_status_overrides": {
                        "timeout-visit": {
                            "status": "timeout",
                            "message": "visit timeout",
                        },
                    },
                },
                "candidates": [
                    {"text": "fatal timeout answer", "score": 2.0},
                    {"text": "ordinary fallback response", "score": 0.2},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-grpo-runtime-fatal-mask",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=normalized_dataset_dir,
        config=config,
        dataset_format="prompt_candidate",
    )

    result = mlx_lm_runner_module.MLXLMRunner(
        policy_runtime=MLXTextRuntime(backend=TimeoutPolicyBackend())
    ).train(request)

    trace_rows = [
        json.loads(line)
        for line in Path(result.metrics.policy_update_trace_path).read_text(encoding="utf-8").splitlines()
    ]
    candidate_trace_rows = [
        json.loads(line)
        for line in Path(result.metrics.candidate_reward_trace_path).read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    row = trace_rows[0]
    timeout_trace = candidate_trace_rows[0]
    safe_trace = candidate_trace_rows[1]

    assert row["selected_candidate_index"] == 0
    assert row["fatal_stage"] == "tool_timeout"
    assert row["fatal_state_mask"] is True
    assert row["fatal_state_mask_reason"] == "tool_timeout"
    assert row["grpo_advantage_raw"] == pytest.approx(0.5)
    assert row["grpo_advantage_clamped"] == 0.0
    assert row["group_fatal_candidate_count"] == 1
    assert row["group_advantage_clamped_candidate_count"] == 1
    assert timeout_trace["fatal_aware_grpo_schema_version"] == "melix.fatal_aware_grpo.v1"
    assert timeout_trace["fatal_stage"] == "tool_timeout"
    assert timeout_trace["fatal_state_mask"] is True
    assert timeout_trace["fatal_state_mask_reason"] == "tool_timeout"
    assert timeout_trace["grpo_advantage_raw"] == pytest.approx(0.5)
    assert timeout_trace["grpo_advantage_clamped"] == 0.0
    assert timeout_trace["grpo_advantage_clamp_applied"] is True
    assert timeout_trace["grpo_advantage_clamp_reason"] == "fatal_state_positive_advantage"
    assert timeout_trace["agentic_tool_metrics"]["agentic_tool.timeout_count"] == 1.0
    assert safe_trace["fatal_state_mask"] is False
    assert safe_trace["grpo_advantage_raw"] == pytest.approx(-0.5)
    assert safe_trace["grpo_advantage_clamped"] == pytest.approx(-0.5)
    assert result.metrics.fatal_candidate_count == 1
    assert result.metrics.selected_fatal_candidate_count == 1
    assert result.metrics.advantage_clamped_candidate_count == 1


def test_alignment_runtime_tool_helpers_cover_namespaces_and_invalid_events() -> None:
    from worker.model_ops.rl_alignment_training import (
        _agentic_tool_run_for_generated_candidate,
        _attach_runtime_candidate_tool_evidence,
        _runtime_tool_namespaces,
        _tool_call_from_runtime_event,
    )

    assert _runtime_tool_namespaces({"tools": [{"name": "visit"}, {"name": "visit"}]}) == "visit"
    assert "local_compute" in _runtime_tool_namespaces({})
    assert _agentic_tool_run_for_generated_candidate({}, []) is None

    candidate: dict[str, object] = {}
    _attach_runtime_candidate_tool_evidence(candidate, [], None)
    assert candidate == {}
    _attach_runtime_candidate_tool_evidence(
        candidate,
        [{"id": "call-1", "name": "visit", "arguments": {}}],
        None,
    )
    assert candidate == {"tool_calls": [{"id": "call-1", "name": "visit", "arguments": {}}]}

    with pytest.raises(ModelOperationError) as invalid_json_exc:
        _tool_call_from_runtime_event(
            RuntimeToolCallEvent(
                call_id="bad-json",
                tool_name="visit",
                arguments_json_fragment="{",
            )
        )
    assert invalid_json_exc.value.code == "alignment_generation_failed"

    with pytest.raises(ModelOperationError) as non_object_exc:
        _tool_call_from_runtime_event(
            RuntimeToolCallEvent(
                call_id="bad-args",
                tool_name="visit",
                arguments_json_fragment="[]",
            )
        )
    assert non_object_exc.value.details["tool_name"] == "visit"
