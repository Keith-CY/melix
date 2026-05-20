from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.protocol.python.worker.v1 import common_pb2
from worker.model_ops import mlx_lm_runner as mlx_lm_runner_module
from worker.model_ops import training_config as training_config_module
from worker.model_ops.alignment_rollout_manifest import (
    build_alignment_rollout_manifest_fields_from_training_metrics,
)
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


def _minimal_training_metrics(**overrides: object) -> mlx_lm_runner_module.TrainingMetrics:
    values = {
        "job_duration_ms": 12.0,
        "tokens_seen": 8,
        "examples_seen": 1,
        "loss_final": 0.2,
        "loss_best": 0.2,
        "learning_rate_final": 1e-4,
    }
    values.update(overrides)
    return mlx_lm_runner_module.TrainingMetrics(**values)


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
    assert result.metrics.reward_component_final_answer_mean == pytest.approx(0.6)
    assert result.metrics.reward_component_tool_efficiency_mean == pytest.approx(-1.0)
    assert result.metrics.reward_component_format_mean == pytest.approx(-0.5)
    assert result.metrics.reward_component_fatal_failure_mean == pytest.approx(-1.0)
    assert result.metrics.reward_component_total_mean == pytest.approx(-1.9)
    assert result.metrics.fatal_trace_count == 1
    assert result.metrics.rollout_manifest_schema_version == "melix.alignment_rollout_manifest.v1"
    assert result.metrics.rollout_candidate_count == 2
    assert result.metrics.rollout_reward_policy_id == "melix.agentic_grpo_reward_components.v1"
    assert result.metrics.rollout_reference_model_path == str(tmp_path / "base-model")
    assert len(result.metrics.rollout_trajectory_digest) == 64
    adapter_config = json.loads(result.adapter_config_path.read_text(encoding="utf-8"))
    assert adapter_config["rollout_candidate_count"] == 2
    assert adapter_config["rollout_reward_policy_id"] == result.metrics.rollout_reward_policy_id
    assert adapter_config["rollout_reference_model_path"] == str(tmp_path / "base-model")
    assert adapter_config["rollout_trajectory_digest"] == result.metrics.rollout_trajectory_digest
    assert trace_rows[0]["rollout_candidate_count"] == 2
    assert trace_rows[0]["rollout_reward_policy_id"] == result.metrics.rollout_reward_policy_id
    assert trace_rows[0]["rollout_reference_model_path"] == str(tmp_path / "base-model")
    assert trace_rows[0]["rollout_trajectory_digest"] == result.metrics.rollout_trajectory_digest


def test_grpo_policy_updates_clamp_fatal_positive_advantage_metadata(
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
                "prompt": "Pick the stronger response.",
                "candidates": [
                    {
                        "text": "High scalar answer with fatal continuation.",
                        "score": 0.9,
                        "fatal_stage": "post_fatal_continuation",
                    },
                    {"text": "Safe lower scalar answer.", "score": -0.5},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-grpo-fatal-clamp",
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
    row = trace_rows[0]
    selected_candidate = row["scored_candidates"][0]
    nonfatal_candidate = row["scored_candidates"][1]
    adapter_config = json.loads(result.adapter_config_path.read_text(encoding="utf-8"))

    assert row["selected_candidate_index"] == 0
    assert row["fatal_aware_grpo_schema_version"] == "melix.fatal_aware_grpo.v1"
    assert row["fatal_state_mask"] is True
    assert row["fatal_state_mask_reason"] == "post_fatal_continuation"
    assert row["grpo_advantage_raw"] == pytest.approx(0.2)
    assert row["grpo_advantage_clamped"] == 0.0
    assert row["grpo_advantage_clamp_applied"] is True
    assert row["grpo_advantage_clamp_reason"] == "fatal_state_positive_advantage"
    assert row["group_fatal_candidate_count"] == 1
    assert row["group_advantage_clamped_candidate_count"] == 1
    assert selected_candidate["fatal_state_mask"] is True
    assert selected_candidate["grpo_advantage_raw"] == pytest.approx(0.2)
    assert selected_candidate["grpo_advantage_clamped"] == 0.0
    assert selected_candidate["grpo_advantage_clamp_applied"] is True
    assert nonfatal_candidate["fatal_state_mask"] is False
    assert nonfatal_candidate["grpo_advantage_raw"] == pytest.approx(-0.2)
    assert nonfatal_candidate["grpo_advantage_clamped"] == pytest.approx(-0.2)
    assert result.metrics.fatal_aware_grpo_schema_version == "melix.fatal_aware_grpo.v1"
    assert result.metrics.fatal_candidate_count == 1
    assert result.metrics.selected_fatal_candidate_count == 1
    assert result.metrics.advantage_clamped_candidate_count == 1
    assert adapter_config["fatal_aware_grpo_schema_version"] == "melix.fatal_aware_grpo.v1"
    assert adapter_config["fatal_candidate_count"] == 1
    assert adapter_config["selected_fatal_candidate_count"] == 1
    assert adapter_config["advantage_clamped_candidate_count"] == 1


def test_grpo_policy_updates_track_penalized_unselected_fatal_without_clamp(
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
                "prompt": "Pick the safe response.",
                "candidates": [
                    {
                        "text": "High scalar answer with a fatal tool failure.",
                        "score": 0.6,
                        "fatal_stage": "tool_execution_failure",
                    },
                    {
                        "text": "Lower scalar answer that is safe after penalties.",
                        "score": 0.1,
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-grpo-fatal-penalty-not-selected",
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
    row = trace_rows[0]
    fatal_candidate = row["scored_candidates"][0]
    selected_candidate = row["scored_candidates"][1]
    adapter_config = json.loads(result.adapter_config_path.read_text(encoding="utf-8"))

    assert row["selected_candidate_index"] == 1
    assert row["fatal_state_mask"] is False
    assert row["fatal_stage"] == ""
    assert row["selected_reward"] == pytest.approx(0.1)
    assert row["group_reward_mean"] == pytest.approx(-0.15)
    assert row["group_fatal_candidate_count"] == 1
    assert row["group_advantage_clamped_candidate_count"] == 0
    assert fatal_candidate["reward_components"]["fatal_failure"] == pytest.approx(-1.0)
    assert fatal_candidate["reward_components"]["total"] == pytest.approx(-0.4)
    assert fatal_candidate["fatal_state_mask"] is True
    assert fatal_candidate["fatal_state_mask_reason"] == "tool_execution_failure"
    assert fatal_candidate["grpo_advantage_raw"] == pytest.approx(-0.25)
    assert fatal_candidate["grpo_advantage_clamped"] == pytest.approx(-0.25)
    assert fatal_candidate["grpo_advantage_clamp_applied"] is False
    assert fatal_candidate["grpo_advantage_clamp_reason"] == ""
    assert selected_candidate["fatal_state_mask"] is False
    assert selected_candidate["grpo_advantage_raw"] == pytest.approx(0.25)
    assert selected_candidate["grpo_advantage_clamped"] == pytest.approx(0.25)
    assert result.metrics.fatal_candidate_count == 1
    assert result.metrics.selected_fatal_candidate_count == 0
    assert result.metrics.advantage_clamped_candidate_count == 0
    assert result.metrics.reward_component_fatal_failure_mean == pytest.approx(-0.5)
    assert adapter_config["fatal_candidate_count"] == 1
    assert adapter_config["selected_fatal_candidate_count"] == 0
    assert adapter_config["advantage_clamped_candidate_count"] == 0


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
    assert result.manifest["rollout_manifest_schema_version"] == "melix.alignment_rollout_manifest.v1"
    assert result.manifest["rollout_candidate_count"] == 2
    assert result.manifest["rollout_reward_policy_id"] == "melix.agentic_grpo_reward_components.v1"
    assert result.manifest["rollout_reference_model_path"] == str(tmp_path / "base-model")
    assert result.manifest["rollout_trajectory_digest"] == alignment_manifest["rollout_trajectory_digest"]
    assert alignment_manifest["rollout_manifest_schema_version"] == "melix.alignment_rollout_manifest.v1"
    assert alignment_manifest["rollout_candidate_count"] == 2
    assert alignment_manifest["rollout_reward_policy_id"] == "melix.agentic_grpo_reward_components.v1"
    assert alignment_manifest["rollout_reference_model_path"] == str(tmp_path / "base-model")
    assert len(alignment_manifest["rollout_trajectory_digest"]) == 64
    assert metrics["reward_mean"] == pytest.approx(0.65)
    assert metrics["reward_component_final_answer_mean"] == pytest.approx(0.35)
    assert metrics["reward_component_tool_efficiency_mean"] == pytest.approx(0.2)
    assert metrics["reward_component_format_mean"] == pytest.approx(0.1)
    assert metrics["reward_component_fatal_failure_mean"] == pytest.approx(0.0)
    assert metrics["reward_component_total_mean"] == pytest.approx(0.65)
    assert metrics["fatal_trace_count"] == 0
    assert metrics["fatal_aware_grpo_schema_version"] == "melix.fatal_aware_grpo.v1"
    assert metrics["fatal_candidate_count"] == 0
    assert metrics["selected_fatal_candidate_count"] == 0
    assert metrics["advantage_clamped_candidate_count"] == 0


def test_alignment_rollout_manifest_fields_cover_rlhf_and_reward_model_defaults(
    tmp_path: Path,
) -> None:
    rlhf_fields = build_alignment_rollout_manifest_fields_from_training_metrics(
        metrics=_minimal_training_metrics(),
        alignment_algorithm="rlhf",
        configured_candidate_count=8,
        candidate_scoring_mode="dataset",
        explicit_reference_model_path="",
        default_reference_model_path=str(tmp_path / "base-model"),
        trajectory_provenance={},
        trace_rows=[{"response": "Helpful answer.", "reward_score": 0.9}],
    )
    assert rlhf_fields["rollout_manifest_schema_version"] == "melix.alignment_rollout_manifest.v1"
    assert rlhf_fields["rollout_candidate_count"] == 1
    assert rlhf_fields["rollout_reward_policy_id"] == "melix.rlhf_dataset_reward.v1"
    assert rlhf_fields["rollout_reference_model_path"] == str(tmp_path / "base-model")
    assert len(rlhf_fields["rollout_trajectory_digest"]) == 64

    reward_model_fields = build_alignment_rollout_manifest_fields_from_training_metrics(
        metrics=_minimal_training_metrics(),
        alignment_algorithm="grpo",
        configured_candidate_count=2,
        candidate_scoring_mode="reward_model",
        explicit_reference_model_path="",
        default_reference_model_path=str(tmp_path / "base-model"),
        trajectory_provenance={},
        trace_rows=[{"prompt": "Draft two answers."}],
    )
    assert reward_model_fields["rollout_candidate_count"] == 2
    assert reward_model_fields["rollout_reward_policy_id"] == "melix.reward_model_scoring.v1"
    assert reward_model_fields["rollout_reference_model_path"] == str(tmp_path / "base-model")
    assert len(reward_model_fields["rollout_trajectory_digest"]) == 64

    metrics_fields = build_alignment_rollout_manifest_fields_from_training_metrics(
        metrics=_minimal_training_metrics(
            rollout_manifest_schema_version="melix.alignment_rollout_manifest.v1",
            rollout_candidate_count=3,
            rollout_reward_policy_id="reward-policy.from-metrics",
            rollout_reference_model_path=str(tmp_path / "reference-model"),
            rollout_trajectory_digest="d" * 64,
        ),
        alignment_algorithm="grpo",
        configured_candidate_count=2,
        candidate_scoring_mode="dataset",
        explicit_reference_model_path="",
        default_reference_model_path=str(tmp_path / "base-model"),
        trajectory_provenance={},
        trace_rows=[],
    )
    assert metrics_fields == {
        "rollout_manifest_schema_version": "melix.alignment_rollout_manifest.v1",
        "rollout_candidate_count": 3,
        "rollout_reward_policy_id": "reward-policy.from-metrics",
        "rollout_reference_model_path": str(tmp_path / "reference-model"),
        "rollout_trajectory_digest": "d" * 64,
    }


def test_grpo_reward_component_helpers_cover_explicit_and_edge_paths() -> None:
    from worker.model_ops.rl_alignment_training import (
        _candidate_fatal_stage,
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
    fallback_failed_tool_run = type(
        "ObservationOnlyRun",
        (),
        {
            "metrics": [],
            "observations": [
                "not-an-observation",
                {"status": "failed"},
            ],
        },
    )()
    fallback_timeout_tool_run = type(
        "ObservationOnlyRun",
        (),
        {
            "metrics": [],
            "observations": [
                {"status": "timeout"},
            ],
        },
    )()
    assert (
        _candidate_fatal_stage(
            {},
            {},
            tool_run=fallback_failed_tool_run,
        )
        == "tool_execution_failure"
    )
    assert (
        _candidate_fatal_stage(
            {},
            {},
            tool_run=fallback_timeout_tool_run,
        )
        == "tool_timeout"
    )
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
