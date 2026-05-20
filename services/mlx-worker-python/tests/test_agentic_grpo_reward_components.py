from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.protocol.python.worker.v1 import common_pb2
from worker.model_ops import mlx_lm_runner as mlx_lm_runner_module
from worker.model_ops import training_config as training_config_module
from worker.model_ops.errors import ModelOperationError
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline
from worker.model_ops.training_dataset import load_training_dataset_package


def _write_dataset_package(
    root: Path,
    *,
    manifest_payload: dict[str, object],
    sample_lines: list[str],
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps(manifest_payload) + "\n", encoding="utf-8")
    (root / "samples.jsonl").write_text("\n".join(sample_lines) + "\n", encoding="utf-8")
    return root


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


def test_grpo_policy_updates_persist_reward_components_and_fatal_stage(
    tmp_path: Path,
) -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={"training_mode": "grpo", "grpo_candidate_count": "2"},
        dataset_format="prompt_candidate",
        response_only_supported=False,
        sample_count=1,
    )
    normalized_dataset_dir = tmp_path / "normalized"
    normalized_dataset_dir.mkdir()
    (normalized_dataset_dir / "train.jsonl").write_text(
        json.dumps(
            {
                "prompt": "Use one tool and answer.",
                "tool_budget": 1,
                "fatal_stage": "tool_timeout",
                "tool_calls": [
                    {"id": "visit-1", "name": "visit", "arguments": {"url": "fixture://doc"}},
                    {"id": "visit-2", "name": "visit", "arguments": {"url": "fixture://doc"}},
                ],
                "tool_fixture_context": {
                    "pages": {"fixture://doc": {"title": "Doc", "text": "Evidence."}},
                },
                "candidates": [
                    {
                        "text": "Evidence-backed answer.",
                        "score": 0.8,
                        "format_valid": True,
                    },
                    {
                        "text": "Malformed answer.",
                        "score": 0.4,
                        "format_valid": False,
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-grpo-components",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=normalized_dataset_dir,
        config=config,
        dataset_format="prompt_candidate",
    )

    result = mlx_lm_runner_module.MLXLMRunner().train(request)
    trace_rows = [
        json.loads(line)
        for line in Path(result.metrics.policy_update_trace_path).read_text(encoding="utf-8").splitlines()
    ]

    components = trace_rows[0]["reward_components"]
    assert components == {
        "final_answer": 0.8,
        "tool_efficiency": -1.0,
        "format": 0.0,
        "fatal_failure": -1.0,
        "total": -1.2,
    }
    assert trace_rows[0]["fatal_stage"] == "tool_timeout"
    assert trace_rows[0]["fatal_penalty_applied"] is True
    assert trace_rows[0]["selected_reward"] == pytest.approx(-1.2)
    assert trace_rows[0]["scored_candidates"][0]["reward_components"]["total"] == pytest.approx(-1.2)
    assert trace_rows[0]["scored_candidates"][1]["reward_components"]["total"] == pytest.approx(-2.6)
    assert result.metrics.reward_mean == pytest.approx(-1.9)
    assert result.metrics.reward_component_final_answer_mean == pytest.approx(0.8)
    assert result.metrics.reward_component_tool_efficiency_mean == pytest.approx(-1.0)
    assert result.metrics.reward_component_format_mean == pytest.approx(0.0)
    assert result.metrics.reward_component_fatal_failure_mean == pytest.approx(-1.0)
    assert result.metrics.reward_component_total_mean == pytest.approx(-1.2)
    assert result.metrics.fatal_trace_count == 1


def test_lora_training_pipeline_records_grpo_reward_component_metrics(
    tmp_path: Path,
) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "prompt-candidates",
        manifest_payload={
            "schema_version": "melix.training_dataset_package.v1",
            "dataset_id": "component-prompt-candidates",
            "format": "prompt_candidate",
            "sample_count": 1,
            "version": "1",
        },
        sample_lines=[
            json.dumps(
                {
                    "prompt": "Choose answer.",
                    "reward": {
                        "final_answer": 0.6,
                        "tool_efficiency": 0.2,
                        "format": 0.1,
                    },
                    "candidates": [
                        {"text": "Good answer.", "score": 0.6},
                        {"text": "Weak answer.", "score": 0.1},
                    ],
                }
            )
        ],
    )
    result = LoRATrainingPipeline().run(
        job_id="pipeline-grpo-components",
        request_ext={
            "training_mode": "grpo",
            "dataset_uri": str(dataset_dir),
            "grpo_candidate_count": "2",
            "adapter_name": "component-adapter",
            "iters": "1",
            "target_modules": "q_proj",
        },
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        output_dir=tmp_path / "job",
        jobs_root=tmp_path / "jobs",
    )

    alignment_manifest = json.loads(
        Path(result.manifest["alignment_run_manifest_path"]).read_text(encoding="utf-8")
    )
    metrics = alignment_manifest["metrics"]
    assert metrics["reward_component_final_answer_mean"] == pytest.approx(0.6)
    assert metrics["reward_component_tool_efficiency_mean"] == pytest.approx(0.2)
    assert metrics["reward_component_format_mean"] == pytest.approx(0.1)
    assert metrics["reward_component_fatal_failure_mean"] == pytest.approx(0.0)
    assert metrics["reward_component_total_mean"] == pytest.approx(0.9)
    assert metrics["fatal_trace_count"] == 0


def test_grpo_reward_component_helpers_cover_explicit_and_edge_paths() -> None:
    from worker.model_ops.rl_alignment_training import (
        _reward_component_summary,
        _reward_components_for_candidate,
    )

    explicit = _reward_components_for_candidate(
        sample={},
        candidate={
            "reward": {
                "final_answer": 0.7,
                "tool_efficiency": 0.1,
                "format": 0.2,
            }
        },
        score=0.0,
        tool_run=None,
        include_sample_fatal=False,
    )
    assert explicit["total"] == pytest.approx(1.0)

    candidate_fatal = _reward_components_for_candidate(
        sample={"tool_efficiency": "0.25", "tool_budget": "bad"},
        candidate={"format_score": "-0.5", "fatal_stage": "parser_failure"},
        score=0.4,
        tool_run=None,
        include_sample_fatal=False,
    )
    assert candidate_fatal == {
        "final_answer": 0.4,
        "tool_efficiency": 0.25,
        "format": -0.5,
        "fatal_failure": -1.0,
        "total": -0.85,
    }

    under_budget = _reward_components_for_candidate(
        sample={"tool_budget": "2", "tool_calls": [{"id": "one"}], "format_valid": False},
        candidate={},
        score=0.5,
        tool_run=None,
        include_sample_fatal=False,
    )
    assert under_budget["tool_efficiency"] == pytest.approx(0.0)
    assert under_budget["format"] == pytest.approx(-1.0)
    assert _reward_component_summary([])["total"] == pytest.approx(0.0)


def test_prompt_candidate_normalization_preserves_reward_component_metadata(
    tmp_path: Path,
) -> None:
    package_dir = _write_dataset_package(
        tmp_path / "prompt-candidates-with-components",
        manifest_payload={
            "schema_version": "melix.training_dataset_package.v1",
            "dataset_id": "prompt-candidates-with-components",
            "format": "prompt_candidate",
            "sample_count": 1,
            "version": "1",
        },
        sample_lines=[
            json.dumps(
                {
                    "prompt": "Choose.",
                    "reward_components": {"tool_efficiency": 0.2},
                    "tool_budget": 2,
                    "format_score": 0.1,
                    "fatal_stage": "answer_invalid",
                    "tool_calls": [{"id": "tool-1"}],
                    "tool_fixture_context": {"pages": {}},
                    "tool_context": {"pages": {}},
                    "candidates": [
                        {
                            "text": "A",
                            "score": 1.0,
                            "reward_components": {"final_answer": 1.0},
                            "format_score": 0.3,
                            "fatal_stage": "parser_failure",
                        },
                        {"text": "B", "score": 0.0},
                    ],
                }
            )
        ],
    )

    package = load_training_dataset_package(package_dir)
    sample = package.normalized_samples[0]

    assert sample["reward_components"] == {"tool_efficiency": 0.2}
    assert sample["tool_budget"] == 2
    assert sample["format_score"] == 0.1
    assert sample["fatal_stage"] == "answer_invalid"
    assert sample["tool_calls"] == [{"id": "tool-1"}]
    assert sample["tool_fixture_context"] == {"pages": {}}
    assert sample["tool_context"] == {"pages": {}}
    assert sample["candidates"][0]["reward_components"] == {"final_answer": 1.0}
    assert sample["candidates"][0]["format_score"] == 0.3
    assert sample["candidates"][0]["fatal_stage"] == "parser_failure"


def test_prompt_candidate_normalization_rejects_non_object_rewards(
    tmp_path: Path,
) -> None:
    bad_candidate_package = _write_dataset_package(
        tmp_path / "bad-prompt-candidates",
        manifest_payload={
            "schema_version": "melix.training_dataset_package.v1",
            "dataset_id": "bad-prompt-candidates",
            "format": "prompt_candidate",
            "sample_count": 1,
            "version": "1",
        },
        sample_lines=[
            json.dumps(
                {
                    "prompt": "Choose.",
                    "reward": "bad",
                    "candidates": [
                        {"text": "A", "score": 1.0},
                        {"text": "B", "score": 0.0, "reward": "bad"},
                    ],
                }
            )
        ],
    )

    with pytest.raises(ModelOperationError, match="candidate reward must be a JSON object"):
        load_training_dataset_package(bad_candidate_package)

    bad_sample_package = _write_dataset_package(
        tmp_path / "bad-prompt-candidates-sample",
        manifest_payload={
            "schema_version": "melix.training_dataset_package.v1",
            "dataset_id": "bad-prompt-candidates-sample",
            "format": "prompt_candidate",
            "sample_count": 1,
            "version": "1",
        },
        sample_lines=[
            json.dumps(
                {
                    "prompt": "Choose.",
                    "reward_components": "bad",
                    "candidates": [
                        {"text": "A", "score": 1.0},
                        {"text": "B", "score": 0.0},
                    ],
                }
            )
        ],
    )

    with pytest.raises(ModelOperationError, match="prompt_candidate reward_components must be a JSON object"):
        load_training_dataset_package(bad_sample_package)
