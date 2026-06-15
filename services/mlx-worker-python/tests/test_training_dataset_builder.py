from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from worker.model_ops import training_dataset as training_dataset_module
from worker.model_ops.errors import ModelOperationError
from worker.model_ops.training_dataset import (
    HFDatasetReference,
    ResolvedTrainingDatasetPackage,
    TrainingDatasetPackage,
    build_training_dataset_artifact,
    load_training_dataset_package,
    write_normalized_dataset_snapshot,
)


_REPO_ROOT = Path(__file__).resolve().parents[3]
_TRAINING_FIXTURE_ROOT = _REPO_ROOT / "services" / "mlx-worker-python" / "fixtures" / "training"


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    return path


def test_write_jsonl_rows_streams_each_row_without_joining_the_full_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "rows.jsonl"
    writes: list[str] = []

    class RecordingFile:
        def __enter__(self) -> RecordingFile:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def write(self, chunk: str) -> int:
            writes.append(chunk)
            return len(chunk)

    def fake_open(self: Path, mode: str = "r", *args: object, **kwargs: object) -> RecordingFile:
        assert self == output_path
        assert mode == "w"
        assert kwargs.get("encoding") == "utf-8"
        return RecordingFile()

    monkeypatch.setattr(Path, "open", fake_open)

    training_dataset_module._write_jsonl_rows(
        output_path,
        [
            {"text": "alpha"},
            {"text": "beta"},
        ],
    )

    assert writes == [
        json.dumps({"text": "alpha"}) + "\n",
        json.dumps({"text": "beta"}) + "\n",
    ]


def test_write_jsonl_rows_preserves_the_existing_blank_line_contract_for_empty_inputs(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "empty.jsonl"

    training_dataset_module._write_jsonl_rows(output_path, [])

    assert output_path.read_text(encoding="utf-8") == "\n"


def test_write_normalized_dataset_snapshot_writes_matching_train_and_samples_jsonl(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "dataset-package"
    package_path.mkdir(parents=True, exist_ok=True)
    manifest_path = package_path / "manifest.json"
    samples_path = package_path / "samples.jsonl"

    dataset = TrainingDatasetPackage(
        package_path=package_path,
        manifest_path=manifest_path,
        samples_path=samples_path,
        schema_version="melix.training_dataset_package.v1",
        dataset_id="melix-demo",
        format="prompt_completion",
        sample_count=2,
        version="1",
        normalized_samples=[
            {"prompt": "alpha", "completion": "beta"},
            {"prompt": "gamma", "completion": "delta"},
        ],
        normalized_validation_samples=[
            {"prompt": "holdout", "completion": "answer"},
        ],
        validation_sample_count=1,
        response_only_supported=False,
    )

    snapshot = write_normalized_dataset_snapshot(dataset, output_dir=tmp_path / "exports")

    assert snapshot.samples_path.read_text(encoding="utf-8") == (
        '{"prompt": "alpha", "completion": "beta"}\n'
        '{"prompt": "gamma", "completion": "delta"}\n'
    )
    assert snapshot.train_path.read_text(encoding="utf-8") == snapshot.samples_path.read_text(encoding="utf-8")
    assert snapshot.valid_path is not None
    assert snapshot.valid_path.read_text(encoding="utf-8") == (
        '{"prompt": "holdout", "completion": "answer"}\n'
    )


def test_write_normalized_dataset_snapshot_applies_manifest_overrides(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "dataset-package"
    package_path.mkdir(parents=True, exist_ok=True)
    stale_agentic_train_path = (
        tmp_path / "exports" / "normalized_dataset" / "agentic-traces.train.jsonl"
    )
    stale_agentic_valid_path = (
        tmp_path / "exports" / "normalized_dataset" / "agentic-traces.valid.jsonl"
    )
    stale_agentic_train_path.parent.mkdir(parents=True, exist_ok=True)
    stale_agentic_train_path.write_text("stale\n", encoding="utf-8")
    stale_agentic_valid_path.write_text("stale\n", encoding="utf-8")
    dataset = TrainingDatasetPackage(
        package_path=package_path,
        manifest_path=package_path / "manifest.json",
        samples_path=package_path / "samples.jsonl",
        schema_version="melix.training_dataset_package.v1",
        dataset_id="melix-demo",
        format="prompt_completion",
        sample_count=1,
        version="1",
        normalized_samples=[{"prompt": "alpha", "completion": "beta"}],
        normalized_validation_samples=[],
        validation_sample_count=0,
        response_only_supported=False,
        manifest_fields={"trajectory_schema_version": "ignored-for-non-agentic"},
    )

    snapshot = write_normalized_dataset_snapshot(
        dataset,
        output_dir=tmp_path / "exports",
        manifest_overrides={
            "validation_strategy": "hf_split",
            "validation_sample_count": 3,
            "hf_valid_split": "validation",
        },
    )

    payload = json.loads(snapshot.manifest_path.read_text(encoding="utf-8"))
    assert payload["dataset_id"] == "melix-demo"
    assert payload["validation_strategy"] == "hf_split"
    assert payload["validation_sample_count"] == 3
    assert payload["hf_valid_split"] == "validation"
    assert "trajectory_quality_metrics" not in payload
    assert "trajectory_trace_digest" not in payload
    assert "trajectory_schema_version" not in payload
    assert stale_agentic_train_path.exists() is False
    assert stale_agentic_valid_path.exists() is False
    assert training_dataset_module.trainer_sample_counts(dataset) == (1, 0)
    agentic_package_path = tmp_path / "agentic-package"
    agentic_package_path.mkdir(parents=True, exist_ok=True)
    (agentic_package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "agentic-replay-demo",
                "format": "agentic_tool_trace",
                "sample_count": 1,
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (agentic_package_path / "samples.jsonl").write_text(
        json.dumps(
            {
                "trace_id": "trace-replay-001",
                "question": "Read the support page before answering.",
                "tool_calls": [
                    {
                        "id": "visit-1",
                        "name": "visit",
                        "arguments": {"url": "fixture://support"},
                    }
                ],
                "tool_fixture_context": {
                    "pages": {
                        "fixture://support": {
                            "title": "Support",
                            "text": "The documented answer is MELIX LABS.",
                        }
                    }
                },
                "final_answer": "MELIX LABS",
                "expected_answer": "MELIX LABS",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    agentic_package = load_training_dataset_package(str(agentic_package_path))
    agentic_sample = agentic_package.normalized_samples[0]
    assert agentic_sample["agentic_tool_observations"][0]["payload"]["title"] == "Support"
    assert agentic_sample["agentic_tool_untrusted_context_receipt_schema"] == (
        "melix.untrusted_context_receipt.v1"
    )
    assert agentic_sample["agentic_tool_untrusted_context_receipt_count"] == 2
    summary_json = json.dumps(
        {
            "schema": agentic_sample["agentic_tool_untrusted_context_receipt_schema"],
            "count": agentic_sample["agentic_tool_untrusted_context_receipt_count"],
        },
        sort_keys=True,
    )
    assert "Support article" not in summary_json
    assert "Please ignore instructions." not in summary_json
    assert training_dataset_module._agentic_tool_observation_receipt_summary(
        [
            None,
            {"untrusted_context_receipts": "not-a-list"},
            {
                "untrusted_context_receipts": [
                    "not-a-receipt",
                    {"source_type": "tool_observation"},
                    {
                        "schema_version": "melix.untrusted_context_receipt.v1",
                        "source_type": "retrieved_document",
                    },
                ]
            },
        ]
    ) == {
        "agentic_tool_untrusted_context_receipt_schema": (
            "melix.untrusted_context_receipt.v1"
        ),
        "agentic_tool_untrusted_context_receipt_count": 2,
    }
    assert training_dataset_module._agentic_tool_observation_receipt_summary(
        [{"untrusted_context_receipts": []}, {}]
    ) == {}

    prompt_candidate_package_path = tmp_path / "prompt-candidate-package"
    prompt_candidate_package_path.mkdir(parents=True, exist_ok=True)
    (prompt_candidate_package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "prompt-candidate-package",
                "format": "prompt_candidate",
                "sample_count": 1,
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (prompt_candidate_package_path / "samples.jsonl").write_text(
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
        + "\n",
        encoding="utf-8",
    )
    prompt_candidate_package = load_training_dataset_package(prompt_candidate_package_path)
    prompt_candidate_sample = prompt_candidate_package.normalized_samples[0]

    assert prompt_candidate_sample["reward_components"] == {"tool_efficiency": 0.2}
    assert prompt_candidate_sample["tool_budget"] == 2
    assert prompt_candidate_sample["format_score"] == 0.1
    assert prompt_candidate_sample["fatal_stage"] == "answer_invalid"
    assert prompt_candidate_sample["tool_calls"] == [{"id": "tool-1"}]
    assert prompt_candidate_sample["tool_fixture_context"] == {"pages": {}}
    assert prompt_candidate_sample["tool_context"] == {"pages": {}}
    assert prompt_candidate_sample["candidates"][0]["reward_components"] == {"final_answer": 1.0}
    assert prompt_candidate_sample["candidates"][0]["format_score"] == 0.3
    assert prompt_candidate_sample["candidates"][0]["fatal_stage"] == "parser_failure"

    bad_prompt_candidate_package_path = tmp_path / "bad-prompt-candidate-package"
    bad_prompt_candidate_package_path.mkdir(parents=True, exist_ok=True)
    (bad_prompt_candidate_package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "bad-prompt-candidate-package",
                "format": "prompt_candidate",
                "sample_count": 1,
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (bad_prompt_candidate_package_path / "samples.jsonl").write_text(
        json.dumps(
            {
                "prompt": "Choose.",
                "reward_components": "bad",
                "candidates": [
                    {"text": "A", "score": 1.0},
                    {"text": "B", "score": 0.0, "reward": "bad"},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ModelOperationError, match="candidate reward must be a JSON object"):
        load_training_dataset_package(bad_prompt_candidate_package_path)

    (bad_prompt_candidate_package_path / "samples.jsonl").write_text(
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
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ModelOperationError, match="prompt_candidate reward_components must be a JSON object"):
        load_training_dataset_package(bad_prompt_candidate_package_path)

    chat_package_path = tmp_path / "chat-package"
    chat_package_path.mkdir(parents=True, exist_ok=True)
    (chat_package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "chat-package",
                "format": "chat_messages",
                "sample_count": 1,
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (chat_package_path / "samples.jsonl").write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Inspect image one.",
                        "media_refs": ["image-1"],
                        "image_token_count": 576,
                    },
                    {"role": "assistant", "content": "The sign says stop."},
                ],
                "media_refs": [
                    {
                        "id": "image-1",
                        "uri": "images/one.jpg",
                        "media_token_count": 576,
                    }
                ],
                "media_token_count": 576,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    chat_package = load_training_dataset_package(chat_package_path)
    chat_sample = chat_package.normalized_samples[0]

    assert chat_sample["messages"][0]["media_refs"] == ["image-1"]
    assert chat_sample["messages"][0]["image_token_count"] == 576
    assert chat_sample["media_refs"] == [
        {
            "id": "image-1",
            "uri": "images/one.jpg",
            "media_token_count": 576,
        }
    ]
    assert chat_sample["media_token_count"] == 576

    agentic_package_path = tmp_path / "agentic-package"
    agentic_package_path.mkdir(parents=True, exist_ok=True)
    samples = [
        {
            "trace_id": "trace-train",
            "question": "Which label is visible?",
            "media_refs": [{"id": "image-1", "uri": "images/sign-one.jpg"}],
            "tools": [{"name": "image_crop"}],
            "turns": [
                {"role": "user", "content": "Inspect image one.", "media_refs": ["image-1"]},
                {
                    "role": "assistant",
                    "tool_call": {
                        "id": "call-1",
                        "name": "image_crop",
                        "arguments": {"media_ref": "image-1"},
                    },
                },
                {
                    "role": "tool",
                    "tool_call_id": "call-1",
                    "observation": {"text": "The sign reads MELIX LABS."},
                },
                {"role": "assistant", "content": "The sign says MELIX LABS."},
            ],
            "final_answer": "MELIX LABS",
            "reward": {"final_answer": 1.0},
            "fatal_stage": "",
        }
    ]
    validation_samples = [
        {
            "trace_id": "trace-valid",
            "question": "Which label is hidden?",
            "media_refs": [{"id": "image-2", "uri": "images/sign-two.jpg"}],
            "turns": [
                {"role": "user", "content": "Inspect image two."},
                {"role": "assistant", "content": "The label says GOLD-SECRET."},
            ],
            "final_answer": "GOLD-SECRET",
            "fatal_stage": "observation_leak",
            "leakage_terms": ["GOLD-SECRET"],
        }
    ]
    agentic_dataset = TrainingDatasetPackage(
        package_path=agentic_package_path,
        manifest_path=agentic_package_path / "manifest.json",
        samples_path=agentic_package_path / "samples.jsonl",
        schema_version="melix.training_dataset_package.v1",
        dataset_id="agentic-package",
        format="agentic_tool_trace",
        sample_count=1,
        version="2026-05-19",
        normalized_samples=samples,
        normalized_validation_samples=validation_samples,
        validation_sample_count=1,
        response_only_supported=True,
        manifest_fields={
            "schema_version": "melix.training_dataset_package.v1",
            "dataset_id": "agentic-package",
            "format": "agentic_tool_trace",
            "sample_count": 1,
            "version": "2026-05-19",
            "trajectory_schema_version": "melix.agentic_tool_trace.v1",
            "toolset_version": "melix.agentic_tools.builtin.v1",
            "registry_schema_version": "melix.agentic_tool_registry.v1",
            "reward_policy_id": "reward-policy.v1",
            "leakage_policy_id": "leakage-policy.v1",
            "source_dataset_id": "source-agentic-package",
            "source_split": "train",
            "source_revision": "rev-123",
            "license": "MIT",
            "media_root": "images/",
        },
    )
    assert training_dataset_module.trainer_sample_counts(agentic_dataset) == (2, 1)

    agentic_snapshot = write_normalized_dataset_snapshot(
        agentic_dataset,
        output_dir=tmp_path / "agentic-exports",
        manifest_overrides={"validation_strategy": "source_validation"},
    )
    agentic_payload = json.loads(agentic_snapshot.manifest_path.read_text(encoding="utf-8"))
    mutated_samples = [dict(samples[0], final_answer="Changed")]

    assert agentic_payload["format"] == "agentic_tool_trace"
    assert agentic_payload["trainer_format"] == "chat_messages"
    assert agentic_payload["agentic_sft_formatter"] == "melix.agentic_tool_trace.sft_formatter.v1"
    assert (
        agentic_payload["agentic_sft_boundary_policy"]
        == "melix.agentic_tool_trace.response_only_boundaries.v1"
    )
    assert agentic_payload["sample_count"] == 2
    assert agentic_payload["validation_sample_count"] == 1
    assert agentic_payload["source_trace_sample_count"] == 1
    assert agentic_payload["source_trace_validation_sample_count"] == 1
    assert agentic_payload["trainer_sample_count"] == 2
    assert agentic_payload["trainer_validation_sample_count"] == 1
    assert agentic_payload["response_only_supported"] is True
    assert agentic_payload["agentic_trace_train_path"].endswith(
        "normalized_dataset/agentic-traces.train.jsonl"
    )
    assert agentic_payload["agentic_trace_valid_path"].endswith(
        "normalized_dataset/agentic-traces.valid.jsonl"
    )
    assert agentic_payload["agentic_sft_projection_metrics"] == {
        "sample_count": 2,
        "trainer_row_count": 3,
        "tool_call_count": 1,
        "tool_observation_count": 1,
        "media_ref_count": 2,
        "final_answer_count": 2,
        "response_only_boundary_count": 3,
        "mask_prompt_boundary_count": 3,
    }
    assert agentic_payload[
        "agentic_sft_token_metrics"
    ] == training_dataset_module.agentic_sft_formatter.merge_token_metrics(
        training_dataset_module.agentic_sft_formatter.collect_token_metrics(samples),
        training_dataset_module.agentic_sft_formatter.collect_token_metrics(
            validation_samples
        ),
    )
    assert agentic_payload["agentic_sft_token_metrics"]["estimator"] == "whitespace_v1"
    assert agentic_payload["agentic_sft_token_metrics"]["source_trace_count"] == 2
    assert agentic_payload["agentic_sft_token_metrics"]["trace_tokens"] > 0
    assert agentic_payload["agentic_sft_token_metrics"]["tool_call_tokens"] > 0
    assert agentic_payload["agentic_sft_token_metrics"]["observation_tokens"] > 0
    assert agentic_payload["agentic_sft_token_metrics"]["final_answer_tokens"] > 0
    assert agentic_payload["source_package_path"] == str(agentic_package_path)
    assert agentic_payload["source_dataset_id"] == "source-agentic-package"
    assert agentic_payload["source_manifest_fields"] == {
        "trajectory_schema_version": "melix.agentic_tool_trace.v1",
        "toolset_version": "melix.agentic_tools.builtin.v1",
        "registry_schema_version": "melix.agentic_tool_registry.v1",
        "reward_policy_id": "reward-policy.v1",
        "leakage_policy_id": "leakage-policy.v1",
        "source_dataset_id": "source-agentic-package",
        "source_split": "train",
        "source_revision": "rev-123",
        "license": "MIT",
        "media_root": "images/",
    }
    assert agentic_payload["trajectory_schema_version"] == "melix.agentic_tool_trace.v1"
    assert agentic_payload["trajectory_split"] == "train"
    assert agentic_payload["trajectory_toolset_version"] == "melix.agentic_tools.builtin.v1"
    assert (
        agentic_payload["trajectory_registry_schema_version"]
        == "melix.agentic_tool_registry.v1"
    )
    assert agentic_payload["trajectory_reward_policy_id"] == "reward-policy.v1"
    assert agentic_payload["trajectory_leakage_policy_id"] == "leakage-policy.v1"
    assert agentic_payload["trajectory_trace_digest"] == training_dataset_module._agentic_trace_digest(
        samples + validation_samples
    )
    assert agentic_payload["trajectory_trace_digest"] != training_dataset_module._agentic_trace_digest(
        mutated_samples + validation_samples
    )
    assert agentic_payload["trajectory_quality_metrics"] == {
        "duplicate_count": 0,
        "duplicate_sample_indices": [],
        "dirty_count": 1,
        "dirty_samples": [{"index": 1, "reasons": ["leakage_terms"]}],
        "agentic_trace_count": 2,
        "trace_turn_count_min": 2,
        "trace_turn_count_max": 4,
        "trace_turn_count_avg": 3.0,
        "tool_call_count": 1,
        "tool_observation_count": 1,
        "media_ref_count": 2,
        "reward_coverage_count": 1,
        "fatal_stage_coverage_count": 2,
        "fatal_trace_count": 1,
        "leakage_count": 1,
        "leakage_samples": [
            {"index": 1, "trace_id": "trace-valid", "terms": ["GOLD-SECRET"]}
        ],
    }
    assert agentic_snapshot.format == "agentic_tool_trace"
    assert agentic_snapshot.trainer_format == "chat_messages"
    assert agentic_snapshot.sample_count == 2
    assert agentic_snapshot.validation_sample_count == 1
    train_rows = [
        json.loads(line)
        for line in agentic_snapshot.train_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(train_rows) == 2
    assert train_rows[0]["tools"] == [{"name": "image_crop"}]
    assert train_rows[0]["response_only_boundary"] == {
        "policy_id": "melix.agentic_tool_trace.response_only_boundaries.v1",
        "mask_prompt": True,
        "trainable_role": "assistant",
        "trainable_kind": "tool_call",
        "trainable_message_index": 2,
        "trace_id": "trace-train",
    }
    assert train_rows[0]["messages"] == [
        {
            "role": "system",
            "content": "Media references:\n- id=image-1; uri=images/sign-one.jpg",
        },
        {"role": "user", "content": "Inspect image one."},
        {
            "role": "assistant",
            "content": (
                'Tool call: {"arguments":{"media_ref":"image-1"},"id":"call-1",'
                '"name":"image_crop"}'
            ),
        },
    ]
    assert train_rows[1]["tools"] == [{"name": "image_crop"}]
    assert train_rows[1]["response_only_boundary"] == {
        "policy_id": "melix.agentic_tool_trace.response_only_boundaries.v1",
        "mask_prompt": True,
        "trainable_role": "assistant",
        "trainable_kind": "final_answer",
        "trainable_message_index": 4,
        "trace_id": "trace-train",
    }
    assert train_rows[1]["messages"] == [
        {
            "role": "system",
            "content": "Media references:\n- id=image-1; uri=images/sign-one.jpg",
        },
        {"role": "user", "content": "Inspect image one."},
        {
            "role": "assistant",
            "content": (
                'Tool call: {"arguments":{"media_ref":"image-1"},"id":"call-1",'
                '"name":"image_crop"}'
            ),
        },
        {
            "role": "tool",
            "content": (
                'Tool observation for call-1: {"text":"The sign reads MELIX LABS."}'
            ),
        },
        {
            "role": "assistant",
            "content": "The sign says MELIX LABS.\n\nFinal answer: MELIX LABS",
        },
    ]
    assert json.loads(
        (agentic_snapshot.dataset_dir / "agentic-traces.train.jsonl").read_text(
            encoding="utf-8"
        )
    ) == samples[0]
    assert agentic_snapshot.valid_path is not None
    valid_row = json.loads(agentic_snapshot.valid_path.read_text(encoding="utf-8"))
    assert valid_row["response_only_boundary"] == {
        "policy_id": "melix.agentic_tool_trace.response_only_boundaries.v1",
        "mask_prompt": True,
        "trainable_role": "assistant",
        "trainable_kind": "final_answer",
        "trainable_message_index": 2,
        "trace_id": "trace-valid",
    }
    assert valid_row["messages"][-1] == {
        "role": "assistant",
        "content": "The label says GOLD-SECRET.\n\nFinal answer: GOLD-SECRET",
    }
    assert json.loads(
        (agentic_snapshot.dataset_dir / "agentic-traces.valid.jsonl").read_text(
            encoding="utf-8"
        )
    ) == validation_samples[0]


def test_write_normalized_dataset_snapshot_clears_stale_valid_jsonl_when_no_validation_samples(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "dataset-package"
    package_path.mkdir(parents=True, exist_ok=True)
    stale_valid_path = tmp_path / "exports" / "normalized_dataset" / "valid.jsonl"
    stale_valid_path.parent.mkdir(parents=True, exist_ok=True)
    stale_valid_path.write_text("stale\n", encoding="utf-8")

    dataset = TrainingDatasetPackage(
        package_path=package_path,
        manifest_path=package_path / "manifest.json",
        samples_path=package_path / "samples.jsonl",
        schema_version="melix.training_dataset_package.v1",
        dataset_id="melix-demo",
        format="prompt_completion",
        sample_count=2,
        version="1",
        normalized_samples=[
            {"prompt": "alpha", "completion": "beta"},
            {"prompt": "gamma", "completion": "delta"},
        ],
        normalized_validation_samples=[],
        validation_sample_count=0,
        response_only_supported=False,
    )

    snapshot = write_normalized_dataset_snapshot(dataset, output_dir=tmp_path / "exports")

    expected_payload = (
        '{"prompt": "alpha", "completion": "beta"}\n'
        '{"prompt": "gamma", "completion": "delta"}\n'
    )
    assert snapshot.samples_path.read_text(encoding="utf-8") == expected_payload
    assert snapshot.train_path.read_text(encoding="utf-8") == expected_payload
    assert snapshot.valid_path is None
    assert stale_valid_path.exists() is False



def test_load_training_dataset_package_respects_sample_limit_after_skipping_blank_lines(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "limited-package"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "limited-package",
                "format": "text_completion",
                "sample_count": 2,
                "version": "1",
                "validation_sample_count": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (package_path / "samples.jsonl").write_text(
        "\n"
        '{"text": "alpha"}\n'
        "\n"
        '{"text": "beta"}\n',
        encoding="utf-8",
    )

    package = load_training_dataset_package(str(package_path), sample_limit=1)

    assert package.sample_count == 1
    assert package.normalized_samples == [{"text": "alpha"}]



def test_load_training_dataset_package_stops_reading_after_sample_limit(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "limited-invalid-tail"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "limited-invalid-tail",
                "format": "text_completion",
                "sample_count": 2,
                "version": "1",
                "validation_sample_count": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (package_path / "samples.jsonl").write_text(
        '{"text": "alpha"}\n'
        "{not-json\n",
        encoding="utf-8",
    )

    package = load_training_dataset_package(str(package_path), sample_limit=1)

    assert package.sample_count == 1
    assert package.normalized_samples == [{"text": "alpha"}]


def test_load_training_dataset_package_limits_validation_samples(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "limited-validation-package"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "limited-validation-package",
                "format": "text_completion",
                "sample_count": 1,
                "version": "1",
                "validation_sample_count": 2,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (package_path / "samples.jsonl").write_text(
        '{"text": "alpha"}\n',
        encoding="utf-8",
    )
    (package_path / "valid.jsonl").write_text(
        "\n"
        '{"text": "holdout-one"}\n'
        "\n"
        '{"text": "holdout-two"}\n',
        encoding="utf-8",
    )

    package = load_training_dataset_package(str(package_path), sample_limit=1)

    assert package.validation_sample_count == 1
    assert package.normalized_validation_samples == [{"text": "holdout-one"}]


def test_load_training_dataset_package_stops_reading_validation_after_sample_limit(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "limited-validation-invalid-tail"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "limited-validation-invalid-tail",
                "format": "text_completion",
                "sample_count": 1,
                "version": "1",
                "validation_sample_count": 2,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (package_path / "samples.jsonl").write_text(
        '{"text": "alpha"}\n',
        encoding="utf-8",
    )
    (package_path / "valid.jsonl").write_text(
        '{"text": "holdout-one"}\n'
        "{not-json\n",
        encoding="utf-8",
    )

    package = load_training_dataset_package(str(package_path), sample_limit=1)

    assert package.validation_sample_count == 1
    assert package.normalized_validation_samples == [{"text": "holdout-one"}]


def test_load_training_dataset_package_supports_preference_pair_samples(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "preference-package"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "preference-package",
                "format": "preference_pair",
                "sample_count": 2,
                "version": "1",
                "validation_sample_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (package_path / "samples.jsonl").write_text(
        '{"prompt": "Choose a greeting.", "chosen": "Hello.", "rejected": "Goodbye."}\n'
        '{"prompt": "Pick the safer answer.", "chosen": "Use the guide.", "rejected": "Guess."}\n',
        encoding="utf-8",
    )
    (package_path / "valid.jsonl").write_text(
        '{"prompt": "Holdout?", "chosen": "Yes.", "rejected": "No."}\n',
        encoding="utf-8",
    )

    package = load_training_dataset_package(str(package_path))

    assert package.format == "preference_pair"
    assert package.response_only_supported is False
    assert package.normalized_samples == [
        {"prompt": "Choose a greeting.", "chosen": "Hello.", "rejected": "Goodbye."},
        {"prompt": "Pick the safer answer.", "chosen": "Use the guide.", "rejected": "Guess."},
    ]
    assert package.normalized_validation_samples == [
        {"prompt": "Holdout?", "chosen": "Yes.", "rejected": "No."}
    ]


def test_load_training_dataset_package_rejects_incomplete_preference_pair_samples(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "invalid-preference-package"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "invalid-preference-package",
                "format": "preference_pair",
                "sample_count": 1,
                "version": "1",
                "validation_sample_count": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (package_path / "samples.jsonl").write_text(
        '{"prompt": "Choose.", "chosen": "A"}\n',
        encoding="utf-8",
    )

    with pytest.raises(ModelOperationError) as exc:
        load_training_dataset_package(str(package_path))

    assert exc.value.code == "invalid_dataset_package"


@pytest.mark.parametrize(
    ("format_name", "sample", "expected"),
    [
        (
            "prompt_candidate",
            {
                "prompt": "Generate options.",
                "candidates": [
                    {"text": "Candidate A", "score": 0.7},
                    {"text": "Candidate B", "score": 0.5},
                ],
            },
            {
                "prompt": "Generate options.",
                "candidates": [
                    {"text": "Candidate A", "score": 0.7},
                    {"text": "Candidate B", "score": 0.5},
                ],
            },
        ),
        (
            "reward_scored",
            {
                "prompt": "Rate this.",
                "response": "A helpful response.",
                "reward_score": 0.83,
            },
            {
                "prompt": "Rate this.",
                "response": "A helpful response.",
                "reward_score": 0.83,
            },
        ),
        (
            "calibration",
            {"text": "Calibration sample text."},
            {"text": "Calibration sample text."},
        ),
    ],
)
def test_load_training_dataset_package_supports_alignment_and_calibration_contracts(
    tmp_path: Path,
    format_name: str,
    sample: dict[str, object],
    expected: dict[str, object],
) -> None:
    package_path = tmp_path / f"{format_name}-package"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": f"{format_name}-package",
                "format": format_name,
                "sample_count": 1,
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (package_path / "samples.jsonl").write_text(
        json.dumps(sample) + "\n",
        encoding="utf-8",
    )

    package = load_training_dataset_package(str(package_path))

    assert package.format == format_name
    assert package.response_only_supported is False
    assert package.normalized_samples == [expected]


def test_load_training_dataset_package_supports_agentic_tool_trace_contract(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "agentic-tool-trace-package"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "agentic-tool-trace-package",
                "format": "agentic_tool_trace",
                "sample_count": 1,
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    sample = {
        "trace_id": "trace-001",
        "question": "Which label is visible in the image?",
        "media_refs": [
            {
                "id": "image-1",
                "uri": "images/sign.jpg",
                "mime_type": "image/jpeg",
                "sha256": "abc123",
            }
        ],
        "tools": [
            {
                "name": "image_crop",
                "schema_version": "melix.tool.image_crop.v1",
            }
        ],
        "turns": [
            {
                "role": "user",
                "content": "Read the label.",
                "media_refs": ["image-1"],
            },
            {
                "role": "assistant",
                "tool_call": {
                    "id": "call-1",
                    "name": "image_crop",
                    "arguments": {"media_ref": "image-1", "region": "center"},
                },
            },
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "observation": {
                    "text": "The cropped region contains the label MELIX LABS.",
                    "evidence_ids": ["image-1"],
                },
            },
            {
                "role": "assistant",
                "content": "The label says MELIX LABS.",
            },
        ],
        "final_answer": "MELIX LABS",
        "expected_answer": "MELIX LABS",
        "evidence_ids": ["image-1"],
        "reward": {"final_answer": 1.0, "tool_efficiency": 0.8},
        "fatal_stage": "",
    }
    (package_path / "samples.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")

    package = load_training_dataset_package(str(package_path))

    assert package.format == "agentic_tool_trace"
    assert package.normalized_samples == [sample]


def test_load_training_dataset_package_replays_agentic_tool_calls_with_shared_runtime(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "agentic-tool-replay-package"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "agentic-tool-replay-package",
                "format": "agentic_tool_trace",
                "sample_count": 1,
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    sample = {
        "trace_id": "trace-replay-001",
        "question": "Read the support page before answering.",
        "tool_calls": [
            {
                "id": "visit-1",
                "name": "visit",
                "arguments": {"url": "fixture://support"},
            }
        ],
        "tool_fixture_context": {
            "pages": {
                "fixture://support": {
                    "title": "Support",
                    "text": "The documented answer is MELIX LABS.",
                }
            }
        },
        "final_answer": "MELIX LABS",
        "expected_answer": "MELIX LABS",
    }
    (package_path / "samples.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")

    package = load_training_dataset_package(str(package_path))
    normalized = package.normalized_samples[0]
    quality, token_stats = training_dataset_module._build_quality_and_token_stats(
        package.normalized_samples,
        package.format,
    )

    assert package.format == "agentic_tool_trace"
    assert normalized["turns"][0] == {
        "role": "user",
        "content": "Read the support page before answering.",
    }
    assert normalized["turns"][1]["tool_call"]["name"] == "visit"
    assert normalized["turns"][2]["observation"]["schema_version"] == "melix.agentic_tool_observation.v1"
    assert normalized["turns"][2]["observation"]["payload"]["text"] == "The documented answer is MELIX LABS."
    assert normalized["turns"][3] == {"role": "assistant", "content": "MELIX LABS"}
    assert normalized["agentic_tool_registry"]["toolset_version"] == "melix.agentic_tools.builtin.v1"
    assert normalized["agentic_tool_calls"][0]["name"] == "visit"
    assert normalized["agentic_tool_observations"][0]["payload"]["title"] == "Support"
    assert normalized["agentic_tool_metrics"]["agentic_tool.call_count"] == 1.0
    assert quality["tool_call_count"] == 1
    assert quality["tool_observation_count"] == 1
    assert token_stats["sample_count"] == 1

def test_prompt_completion_quality_stats_do_not_import_agentic_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "worker.runtime.agentic_tools", None)

    quality, token_stats = training_dataset_module._build_quality_and_token_stats(
        [
            {"prompt": "alpha", "completion": "beta"},
            {"prompt": "alpha", "completion": "beta"},
        ],
        "prompt_completion",
    )

    assert token_stats["sample_count"] == 2
    assert quality["duplicate_count"] == 1
    assert quality["dirty_count"] == 0


def test_agentic_tool_trace_replay_covers_context_validation_and_preserved_evidence() -> None:
    with pytest.raises(ModelOperationError) as invalid_context_exc:
        training_dataset_module._normalize_sample(
            {
                "trace_id": "trace-invalid-context",
                "question": "Use a tool.",
                "tool_calls": [{"id": "call-1", "name": "visit", "arguments": {"url": "fixture://doc"}}],
                "tool_fixture_context": "not-a-dict",
                "final_answer": "Done.",
            },
            format_name="agentic_tool_trace",
            max_characters_per_sample=0,
        )
    assert invalid_context_exc.value.message == "agentic_tool_trace tool_fixture_context must be a JSON object."

    with pytest.raises(ModelOperationError) as replay_exc:
        training_dataset_module._normalize_sample(
            {
                "trace_id": "trace-invalid-tool",
                "question": "Use a tool.",
                "tool_calls": [{"id": "call-1", "name": "missing_tool", "arguments": {}}],
                "final_answer": "Done.",
            },
            format_name="agentic_tool_trace",
            max_characters_per_sample=0,
        )
    assert replay_exc.value.message.startswith("agentic_tool_trace replay failed:")

    preserved = training_dataset_module._normalize_sample(
        {
            "trace_id": "trace-preserved-evidence",
            "question": "What is recorded?",
            "turns": [{"role": "assistant", "content": "Recorded."}],
            "final_answer": "Recorded.",
            "agentic_tool_registry": {"toolset_version": "demo"},
            "agentic_tool_calls": [{"id": "call-1", "name": "visit", "arguments": {}}],
            "agentic_tool_observations": [{"status": "completed"}],
            "agentic_tool_metrics": {"agentic_tool.call_count": 1.0},
        },
        format_name="agentic_tool_trace",
        max_characters_per_sample=0,
    )
    assert preserved["agentic_tool_registry"] == {"toolset_version": "demo"}
    assert preserved["agentic_tool_calls"][0]["name"] == "visit"
    assert preserved["agentic_tool_observations"][0]["status"] == "completed"
    assert preserved["agentic_tool_metrics"]["agentic_tool.call_count"] == 1.0

    invalid_evidence = {
        "trace_id": "trace-invalid-evidence",
        "question": "What is recorded?",
        "turns": [{"role": "assistant", "content": "Recorded."}],
        "final_answer": "Recorded.",
    }
    for field, value, message in (
        ("agentic_tool_calls", {}, "agentic_tool_trace agentic_tool_calls must be an array."),
        ("agentic_tool_registry", [], "agentic_tool_trace agentic_tool_registry must be a JSON object."),
    ):
        with pytest.raises(ModelOperationError) as evidence_exc:
            training_dataset_module._normalize_sample(
                {**invalid_evidence, field: value},
                format_name="agentic_tool_trace",
                max_characters_per_sample=0,
            )
        assert evidence_exc.value.message == message


@pytest.mark.parametrize(
    ("sample", "expected_message"),
    [
        (
            {
                "trace_id": "empty-turns",
                "question": "What changed?",
                "turns": [],
                "final_answer": "Nothing.",
            },
            "agentic_tool_trace samples must include non-empty turns.",
        ),
        (
            {
                "trace_id": "orphan-observation",
                "question": "What does the tool see?",
                "turns": [
                    {"role": "user", "content": "Inspect it."},
                    {
                        "role": "tool",
                        "tool_call_id": "missing-call",
                        "observation": {"text": "A sign is visible."},
                    },
                    {"role": "assistant", "content": "A sign is visible."},
                ],
                "final_answer": "A sign is visible.",
            },
            "agentic_tool_trace tool observations must reference a prior assistant tool call.",
        ),
    ],
)
def test_load_training_dataset_package_rejects_invalid_agentic_tool_traces(
    tmp_path: Path,
    sample: dict[str, object],
    expected_message: str,
) -> None:
    package_path = tmp_path / "invalid-agentic-tool-trace-package"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "invalid-agentic-tool-trace-package",
                "format": "agentic_tool_trace",
                "sample_count": 1,
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (package_path / "samples.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")

    with pytest.raises(ModelOperationError) as exc:
        load_training_dataset_package(str(package_path))

    assert exc.value.code == "invalid_dataset_package"
    assert exc.value.message == expected_message


def test_build_training_dataset_artifact_reports_agentic_trace_leakage_metrics(
    tmp_path: Path,
) -> None:
    dataset_path = _write_jsonl(
        tmp_path / "agentic-traces.jsonl",
        [
            {
                "trace_id": "trace-clean",
                "question": "Which label is visible in image one?",
                "media_refs": [{"id": "image-1", "uri": "images/one.jpg"}],
                "tools": [{"name": "image_crop"}],
                "turns": [
                    {"role": "user", "content": "Inspect image one."},
                    {
                        "role": "assistant",
                        "tool_call": {
                            "id": "call-1",
                            "name": "image_crop",
                            "arguments": {"media_ref": "image-1"},
                        },
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "call-1",
                        "observation": {"text": "The sign reads MELIX LABS."},
                    },
                    {"role": "assistant", "content": "The sign says MELIX LABS."},
                ],
                "final_answer": "MELIX LABS",
                "expected_answer": "MELIX LABS",
                "evidence_ids": ["image-1"],
                "reward": {"final_answer": 1.0},
                "fatal_stage": "",
            },
            {
                "trace_id": "trace-leaky",
                "question": "Which label is visible in image two?",
                "turns": [
                    {"role": "user", "content": "Inspect image two."},
                    {
                        "role": "assistant",
                        "tool_call": {
                            "id": "call-2",
                            "name": "image_crop",
                            "arguments": {"media_ref": "image-2"},
                        },
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "call-2",
                        "observation": {"text": "Hidden oracle says GOLD-SECRET."},
                    },
                    {"role": "assistant", "content": "The label says GOLD-SECRET."},
                ],
                "final_answer": "GOLD-SECRET",
                "expected_answer": "GOLD-SECRET",
                "leakage_terms": ["GOLD-SECRET"],
                "fatal_stage": "observation_leak",
            },
        ],
    )

    result = build_training_dataset_artifact(
        {
            "dataset_uri": str(dataset_path),
            "template": "auto",
            "dataset_id": "melix-agentic-trace-demo",
            "preview_count": "1",
        },
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "built-agentic-dataset",
        source_model_id="melix-dev-vlm",
    )

    payload = result.manifest_payload
    package = load_training_dataset_package(str(result.package_path))

    assert payload["format"] == "agentic_tool_trace"
    assert payload["conversion_template"] == "agentic_tool_trace"
    assert payload["quality"]["agentic_trace_count"] == 2
    assert payload["quality"]["tool_call_count"] == 2
    assert payload["quality"]["tool_observation_count"] == 2
    assert payload["quality"]["fatal_trace_count"] == 1
    assert payload["quality"]["leakage_count"] == 1
    assert payload["quality"]["leakage_samples"] == [
        {"index": 1, "trace_id": "trace-leaky", "terms": ["GOLD-SECRET"]}
    ]
    assert payload["quality"]["dirty_samples"] == [
        {"index": 1, "reasons": ["leakage_terms"]}
    ]
    assert payload["token_stats"]["prompt_tokens_max"] > 0
    assert payload["token_stats"]["completion_tokens_max"] > 0
    assert package.format == "agentic_tool_trace"
    assert package.normalized_samples[1]["fatal_stage"] == "observation_leak"


def test_agentic_tool_trace_fixture_loads_and_reports_quality_metrics() -> None:
    fixture_path = _TRAINING_FIXTURE_ROOT / "agentic-tool-trace.dev.v1"

    package = load_training_dataset_package(str(fixture_path))
    quality, token_stats = training_dataset_module._build_quality_and_token_stats(
        package.normalized_samples,
        package.format,
    )

    assert package.dataset_id == "agentic-tool-trace.dev.v1"
    assert package.format == "agentic_tool_trace"
    assert package.sample_count == 2
    assert quality["agentic_trace_count"] == 2
    assert quality["tool_call_count"] == 2
    assert quality["tool_observation_count"] == 2
    assert quality["fatal_trace_count"] == 1
    assert quality["leakage_count"] == 1
    assert token_stats["sample_count"] == 2
    assert token_stats["completion_tokens_max"] > 0


def test_agentic_tool_trace_helpers_cover_optional_field_validation_and_segments() -> None:
    sample = {
        "trace_id": "trace-helper",
        "question": "What is in the image?",
        "media_refs": [{"id": "image-helper", "uri": "images/helper.jpg"}],
        "tools": [{"name": "image_crop"}],
        "turns": [
            {"role": "user", "content": "Inspect it.", "media_refs": ["image-helper"]},
            {
                "role": "assistant",
                "tool_call": {
                    "id": "call-helper",
                    "name": "image_crop",
                    "arguments": {"hint": "SECRET-HINT"},
                },
            },
            {
                "role": "tool",
                "tool_call_id": "call-helper",
                "observation": "SECRET-HINT is visible.",
            },
            {"role": "assistant", "content": "SECRET-HINT is visible."},
        ],
        "final_answer": "SECRET-HINT",
        "expected_answer": "SECRET-HINT",
        "evidence_ids": ["image-helper"],
        "leakage_terms": ["SECRET-HINT"],
    }

    normalized = training_dataset_module._normalize_sample(
        sample,
        format_name="agentic_tool_trace",
        max_characters_per_sample=0,
    )

    assert normalized["turns"][2]["observation"] == {"text": "SECRET-HINT is visible."}
    sample["turns"][0]["media_refs"].append("mutated")
    sample["turns"][1]["tool_call"]["arguments"]["hint"] = "MUTATED-HINT"
    sample["media_refs"].append({"id": "mutated"})
    sample["tools"].append({"name": "mutated"})
    sample["evidence_ids"].append("mutated")
    assert normalized["turns"][0]["media_refs"] == ["image-helper"]
    assert normalized["turns"][1]["tool_call"]["arguments"] == {"hint": "SECRET-HINT"}
    assert normalized["media_refs"] == [{"id": "image-helper", "uri": "images/helper.jpg"}]
    assert normalized["tools"] == [{"name": "image_crop"}]
    assert normalized["evidence_ids"] == ["image-helper"]
    assert training_dataset_module._agentic_trace_leakage_terms(normalized) == ["SECRET-HINT"]
    assert training_dataset_module._sample_token_counts(normalized, "agentic_tool_trace")[1] == 1
    assert "SECRET-HINT is visible." in training_dataset_module._sample_text_segments(
        normalized,
        format_name="agentic_tool_trace",
    )
    assert training_dataset_module._convert_local_rows(
        [sample],
        "agentic_tool_trace",
    )[0] == "agentic_tool_trace"
    assert training_dataset_module._resolve_local_conversion_template(
        "agentic_tool_trace",
        {},
    ) == "agentic_tool_trace"
    assert training_dataset_module._resolve_local_conversion_template(
        "auto",
        {
            "trace_id": "trace-auto",
            "tool_calls": [{"name": "visit"}],
            "final_answer": "Done.",
        },
    ) == "agentic_tool_trace"

    invalid_reward = dict(sample)
    invalid_reward["reward"] = 1
    with pytest.raises(ModelOperationError) as invalid_reward_exc:
        training_dataset_module._normalize_sample(
            invalid_reward,
            format_name="agentic_tool_trace",
            max_characters_per_sample=0,
        )
    assert invalid_reward_exc.value.message == "agentic_tool_trace reward must be a JSON object."

    invalid_media = dict(sample)
    invalid_media["media_refs"] = "image-1"
    with pytest.raises(ModelOperationError) as invalid_media_exc:
        training_dataset_module._normalize_sample(
            invalid_media,
            format_name="agentic_tool_trace",
            max_characters_per_sample=0,
        )
    assert invalid_media_exc.value.message == "agentic_tool_trace media_refs must be an array."


def test_agentic_tool_trace_local_conversion_does_not_inject_optional_defaults() -> None:
    minimal_sample = {
        "trace_id": "trace-minimal",
        "question": "What is visible?",
        "turns": [{"role": "assistant", "content": "A sign is visible."}],
        "final_answer": "A sign is visible.",
    }

    format_name, converted = training_dataset_module._convert_local_rows(
        [minimal_sample],
        "agentic_tool_trace",
    )

    assert format_name == "agentic_tool_trace"
    assert converted == [minimal_sample]


def test_agentic_tool_trace_quality_uses_explicit_format_dispatch_and_content_dedup() -> None:
    base_trace = {
        "question": "What is visible?",
        "turns": [
            {"role": "user", "content": "Inspect it."},
            {
                "role": "assistant",
                "tool_call": {
                    "id": "call-1",
                    "name": "image_crop",
                    "arguments": {"media_ref": "image-1"},
                },
            },
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "observation": {"text": "Hidden oracle says SECRET-LABEL."},
            },
            {"role": "assistant", "content": "The sign says SECRET-LABEL."},
        ],
        "final_answer": "SECRET-LABEL",
        "expected_answer": "SECRET-LABEL",
        "leakage_terms": ["SECRET-LABEL"],
    }
    first = {"trace_id": "trace-1", **base_trace}
    second = {"trace_id": "trace-2", **base_trace}
    collision_shape = {
        "trace_id": "not-agentic",
        "turns": [{"role": "assistant", "content": "SECRET-LABEL"}],
        "text": "fallback text",
        "leakage_terms": ["SECRET-LABEL"],
    }

    quality, _ = training_dataset_module._build_quality_and_token_stats(
        [first, second],
        "agentic_tool_trace",
    )

    assert quality["duplicate_count"] == 1
    assert quality["duplicate_sample_indices"] == [1]
    assert training_dataset_module._sample_text_segments(collision_shape) == ["fallback text"]
    assert training_dataset_module._sample_text_segments(
        collision_shape,
        format_name="agentic_tool_trace",
    ) == ["SECRET-LABEL"]
    assert training_dataset_module._dirty_sample_reasons(collision_shape) == []
    assert training_dataset_module._dirty_sample_reasons(
        collision_shape,
        format_name="agentic_tool_trace",
    ) == ["leakage_terms"]


@pytest.mark.parametrize(
    ("sample_patch", "expected_message"),
    [
        (
            {"trace_id": ""},
            "agentic_tool_trace samples must include trace_id, question, and final_answer.",
        ),
        (
            {"turns": ["bad-turn"]},
            "agentic_tool_trace turns must be JSON objects.",
        ),
        (
            {"turns": [{"role": "robot", "content": "Inspect it."}]},
            "agentic_tool_trace turns must use supported roles.",
        ),
        (
            {"turns": [{"role": "user", "content": "  "}]},
            "agentic_tool_trace user and system turns must include content.",
        ),
        (
            {"turns": [{"role": "assistant", "tool_call": {"id": "", "name": "image_crop"}}]},
            "agentic_tool_trace assistant tool calls must include id and name.",
        ),
        (
            {"turns": [{"role": "assistant"}]},
            "agentic_tool_trace assistant turns must include content or a tool_call.",
        ),
        (
            {
                "turns": [
                    {
                        "role": "assistant",
                        "tool_call": {"id": "call-blank", "name": "image_crop"},
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "call-blank",
                        "observation": " ",
                    },
                ]
            },
            "agentic_tool_trace tool observations must be non-empty.",
        ),
        (
            {
                "turns": [
                    {
                        "role": "assistant",
                        "tool_call": {"id": "call-bad-observation", "name": "image_crop"},
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "call-bad-observation",
                        "observation": [],
                    },
                ]
            },
            "agentic_tool_trace tool observations must be non-empty.",
        ),
        (
            {"turns": [{"role": "user", "content": "Inspect it.", "media_refs": "image-1"}]},
            "agentic_tool_trace turn media_refs must be an array.",
        ),
        (
            {"turns": [{"role": "user", "content": "Inspect it."}]},
            "agentic_tool_trace samples must include at least one assistant turn.",
        ),
    ],
)
def test_agentic_tool_trace_normalization_rejects_schema_violations(
    sample_patch: dict[str, object],
    expected_message: str,
) -> None:
    base_sample = {
        "trace_id": "trace-invalid",
        "question": "What is visible?",
        "turns": [
            {"role": "user", "content": "Inspect it."},
            {"role": "assistant", "content": "A sign is visible."},
        ],
        "final_answer": "A sign is visible.",
    }
    sample = {**base_sample, **sample_patch}

    with pytest.raises(ModelOperationError) as exc:
        training_dataset_module._normalize_sample(
            sample,
            format_name="agentic_tool_trace",
            max_characters_per_sample=0,
        )

    assert exc.value.code == "invalid_dataset_package"
    assert exc.value.message == expected_message


def test_agentic_tool_trace_helpers_cover_defensive_non_dict_turn_paths() -> None:
    sample = {
        "trace_id": "trace-defensive",
        "question": "What is visible?",
        "turns": [
            "bad-turn",
            {"role": "assistant", "tool_call": {"id": "call-1", "name": "image_crop"}},
            {"role": "tool", "tool_call_id": "call-1", "observation": "raw observation"},
        ],
        "final_answer": "raw observation",
        "leakage_terms": "not-a-list",
    }
    metrics = training_dataset_module._new_agentic_trace_quality_metrics()

    training_dataset_module._update_agentic_trace_quality_metrics(
        metrics,
        sample,
        index=0,
        sample_limit=1,
    )

    assert metrics["agentic_trace_count"] == 1
    assert metrics["tool_call_count"] == 1
    assert metrics["tool_observation_count"] == 1
    assert training_dataset_module._sample_text_segments(
        sample,
        format_name="agentic_tool_trace",
    ) == [
        "What is visible?",
        "raw observation",
        "image_crop",
        "raw observation",
    ]
    assert training_dataset_module._agentic_trace_leakage_terms(sample) == []
    assert training_dataset_module._agentic_trace_leakage_scan_segments(sample) == [
        "What is visible?",
        "raw observation",
    ]


@pytest.mark.parametrize(
    ("format_name", "sample"),
    [
        ("prompt_candidate", {"prompt": "Only one.", "candidates": [{"text": "A"}]}),
        ("prompt_candidate", {"prompt": "Bad score.", "candidates": [{"text": "A", "score": "bad"}, {"text": "B"}]}),
        ("prompt_candidate", {"prompt": "Bad candidate.", "candidates": [1, {"text": "B"}]}),
        ("prompt_candidate", {"prompt": "Null candidate.", "candidates": [None, {"text": "B"}]}),
        ("prompt_candidate", {"prompt": "Blank candidate.", "candidates": ["", {"text": "B"}]}),
        ("reward_scored", {"prompt": "Missing score.", "response": "A"}),
        ("reward_scored", {"prompt": "Bad score.", "response": "A", "reward_score": "bad"}),
        ("calibration", {"prompt": ""}),
    ],
)
def test_load_training_dataset_package_rejects_incomplete_alignment_and_calibration_contracts(
    tmp_path: Path,
    format_name: str,
    sample: dict[str, object],
) -> None:
    package_path = tmp_path / f"invalid-{format_name}-package"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": f"invalid-{format_name}-package",
                "format": format_name,
                "sample_count": 1,
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (package_path / "samples.jsonl").write_text(
        json.dumps(sample) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ModelOperationError) as exc:
        load_training_dataset_package(str(package_path))

    assert exc.value.code == "invalid_dataset_package"


def test_load_training_dataset_package_reports_null_prompt_candidate(tmp_path: Path) -> None:
    package_path = tmp_path / "invalid-null-prompt-candidate-package"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "invalid-null-prompt-candidate-package",
                "format": "prompt_candidate",
                "sample_count": 1,
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (package_path / "samples.jsonl").write_text(
        json.dumps({"prompt": "Choose.", "candidates": [None, {"text": "B"}]}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ModelOperationError) as exc:
        load_training_dataset_package(str(package_path))

    assert exc.value.code == "invalid_dataset_package"
    assert exc.value.message == "prompt_candidate candidates cannot be null."
    assert exc.value.details["candidate_index"] == "0"


@pytest.mark.parametrize(
    ("row", "expected_format", "expected_samples"),
    [
        (
            {
                "prompt": "Choose.",
                "candidates": ["Candidate A", {"text": "Candidate B", "score": 0.5}],
            },
            "prompt_candidate",
            [
                {
                    "prompt": "Choose.",
                    "candidates": [{"text": "Candidate A"}, {"score": 0.5, "text": "Candidate B"}],
                }
            ],
        ),
        (
            {"prompt": "Rate.", "response": "Helpful.", "reward_score": "0.75"},
            "reward_scored",
            [{"prompt": "Rate.", "response": "Helpful.", "reward_score": 0.75}],
        ),
        (
            {"text": "Calibration text."},
            "text_completion",
            [{"text": "Calibration text."}],
        ),
    ],
)
def test_resolve_local_training_samples_infers_alignment_contracts(
    tmp_path: Path,
    row: dict[str, object],
    expected_format: str,
    expected_samples: list[dict[str, object]],
) -> None:
    rows_path = tmp_path / "rows.jsonl"
    rows_path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    samples, format_name, resolved_template = training_dataset_module._resolve_local_training_samples(
        rows_path,
        template="auto",
        sample_limit=0,
    )

    assert format_name == expected_format
    assert resolved_template == expected_format
    assert samples == expected_samples


@pytest.mark.parametrize(
    ("template", "row", "expected_format", "expected_sample"),
    [
        (
            "prompt_candidate",
            {
                "prompt": "Choose.",
                "candidates": [{"text": "Candidate A"}, {"text": "Candidate B"}],
            },
            "prompt_candidate",
            {
                "prompt": "Choose.",
                "candidates": [{"text": "Candidate A"}, {"text": "Candidate B"}],
            },
        ),
        (
            "reward_scored",
            {"prompt": "Rate.", "response": "Helpful.", "reward_score": 0.75},
            "reward_scored",
            {"prompt": "Rate.", "response": "Helpful.", "reward_score": 0.75},
        ),
        (
            "calibration",
            {"text": "Calibration text."},
            "calibration",
            {"text": "Calibration text."},
        ),
    ],
)
def test_convert_local_rows_supports_explicit_alignment_and_calibration_templates(
    template: str,
    row: dict[str, object],
    expected_format: str,
    expected_sample: dict[str, object],
) -> None:
    format_name, converted = training_dataset_module._convert_local_rows([row], template)

    assert format_name == expected_format
    assert converted == [expected_sample]


def test_alignment_dataset_token_counts_and_text_segments() -> None:
    prompt_candidate = {
        "prompt": "two words",
        "candidates": ["first answer", {"text": "second answer"}],
    }
    reward_scored = {
        "prompt": "rate this",
        "response": "good answer",
        "reward_score": 0.7,
    }

    assert training_dataset_module._sample_token_counts(prompt_candidate, "prompt_candidate") == (2, 4)
    assert training_dataset_module._sample_token_counts(reward_scored, "reward_scored") == (2, 2)
    assert training_dataset_module._sample_text_segments(prompt_candidate) == [
        "two words",
        "first answer",
        "second answer",
    ]
    assert training_dataset_module._sample_text_segments(reward_scored) == [
        "rate this",
        "good answer",
    ]



def test_iter_dataset_package_jsonl_rows_enforces_sample_limit_before_invalid_tail(
    tmp_path: Path,
) -> None:
    rows_path = tmp_path / "rows.jsonl"
    rows_path.write_text(
        '{"text": "alpha"}\n'
        "\n"
        '{"text": "beta"}\n'
        "{not-json\n",
        encoding="utf-8",
    )

    rows = list(
        training_dataset_module._iter_dataset_package_jsonl_rows(
            rows_path,
            invalid_json_message="Training dataset sample is not valid JSON.",
            sample_limit=2,
        )
    )

    assert rows == [{"text": "alpha"}, {"text": "beta"}]



def test_load_training_dataset_package_rejects_invalid_manifest_json(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "invalid-manifest"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text("{not-json", encoding="utf-8")
    (package_path / "samples.jsonl").write_text('{"text": "alpha"}\n', encoding="utf-8")

    with pytest.raises(ModelOperationError) as exc:
        load_training_dataset_package(str(package_path))

    assert exc.value.code == "invalid_dataset_package"



def test_load_training_dataset_package_rejects_invalid_sample_json(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "invalid-sample"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "invalid-sample",
                "format": "text_completion",
                "sample_count": 1,
                "version": "1",
                "validation_sample_count": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (package_path / "samples.jsonl").write_text("{not-json\n", encoding="utf-8")

    with pytest.raises(ModelOperationError) as exc:
        load_training_dataset_package(str(package_path))

    assert exc.value.code == "invalid_dataset_package"



def test_build_training_dataset_artifact_converts_alpaca_rows_and_records_quality_signals(
    tmp_path: Path,
) -> None:
    dataset_path = _write_jsonl(
        tmp_path / "alpaca.jsonl",
        [
            {
                "instruction": "Translate to French.",
                "input": "Hello world",
                "output": "Bonjour le monde",
            },
            {
                "instruction": "Translate to French.",
                "input": "Hello world",
                "output": "Bonjour le monde",
            },
            {
                "instruction": "Repeat the token.",
                "input": "",
                "output": "token\u0000token",
            },
        ],
    )

    result = build_training_dataset_artifact(
        {
            "dataset_uri": str(dataset_path),
            "template": "alpaca",
            "dataset_id": "melix-alpaca-demo",
            "validation_ratio": "0.34",
            "preview_count": "2",
        },
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "built-dataset",
        source_model_id="melix-dev-text",
    )

    payload = result.manifest_payload
    package = load_training_dataset_package(str(result.package_path))

    assert result.output_path == result.package_path
    assert payload["schema_version"] == "melix.training_dataset_package.v1"
    assert payload["dataset_id"] == "melix-alpaca-demo"
    assert payload["format"] == "prompt_completion"
    assert payload["sample_count"] == 2
    assert payload["validation_sample_count"] == 1
    assert payload["validation_strategy"] == "deterministic_ratio"
    assert payload["conversion_template"] == "alpaca"
    assert payload["source_kind"] == "local_path"
    assert len(payload["preview_samples"]) == 2
    assert payload["quality"]["duplicate_count"] == 1
    assert payload["quality"]["dirty_count"] == 1
    assert payload["token_stats"]["estimator"] == "whitespace_v1"
    assert payload["token_stats"]["prompt_tokens_p95"] >= 3
    assert package.dataset_id == "melix-alpaca-demo"
    assert package.format == "prompt_completion"
    assert package.validation_sample_count == 1


def test_build_training_dataset_artifact_converts_preference_pair_rows(
    tmp_path: Path,
) -> None:
    dataset_path = _write_jsonl(
        tmp_path / "preferences.jsonl",
        [
            {
                "prompt": "Choose the concise answer.",
                "chosen": "Use the short answer.",
                "rejected": "Add unrelated details.",
            },
            {
                "prompt": "Choose the concise answer.",
                "chosen": "Use the short answer.",
                "rejected": "Add unrelated details.",
            },
            {
                "prompt": "Pick the better answer.",
                "chosen": "same",
                "rejected": "same",
            },
        ],
    )

    result = build_training_dataset_artifact(
        {
            "dataset_uri": str(dataset_path),
            "template": "auto",
            "dataset_id": "melix-preference-demo",
            "validation_ratio": "0.34",
        },
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "built-preference-dataset",
        source_model_id="melix-dev-text",
    )

    payload = result.manifest_payload
    package = load_training_dataset_package(str(result.package_path))

    assert payload["schema_version"] == "melix.training_dataset_package.v1"
    assert payload["format"] == "preference_pair"
    assert payload["conversion_template"] == "preference_pair"
    assert payload["response_only_supported"] is False
    assert payload["quality"]["duplicate_count"] == 1
    assert payload["quality"]["dirty_count"] == 1
    assert payload["quality"]["dirty_samples"] == [
        {"index": 2, "reasons": ["duplicate_preference_pair"]}
    ]
    assert payload["token_stats"]["prompt_tokens_max"] >= 4
    assert payload["token_stats"]["completion_tokens_max"] >= 6
    assert package.format == "preference_pair"
    assert package.validation_sample_count == 1


def test_build_training_dataset_artifact_inspects_sharegpt_rows_without_writing_a_package(
    tmp_path: Path,
) -> None:
    dataset_path = _write_jsonl(
        tmp_path / "sharegpt.jsonl",
        [
            {
                "conversations": [
                    {"from": "system", "value": "You are helpful."},
                    {"from": "human", "value": "Say hi."},
                    {"from": "gpt", "value": "Hi there."},
                ]
            },
            {
                "conversations": [
                    {"from": "human", "value": "Say bye."},
                    {"from": "gpt", "value": "Bye."},
                ]
            },
        ],
    )

    result = build_training_dataset_artifact(
        {
            "dataset_uri": str(dataset_path),
            "template": "auto",
            "preview_count": "1",
            "inspect_only": "true",
        },
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "dataset-inspect",
        source_model_id="melix-dev-text",
    )

    payload = result.manifest_payload

    assert result.output_path == result.manifest_path
    assert payload["schema_version"] == "melix.training_dataset_inspection.v1"
    assert payload["format"] == "chat_messages"
    assert payload["conversion_template"] == "sharegpt"
    assert payload["sample_count"] == 2
    assert payload["validation_sample_count"] == 0
    assert payload["preview_samples"][0]["messages"][0]["role"] == "system"
    assert payload["preview_samples"][0]["messages"][-1]["role"] == "assistant"
    assert payload["build_ready"] is True
    assert (result.package_path / "samples.jsonl").exists() is False


def test_build_training_dataset_artifact_materializes_hf_source_and_clears_stale_validation_file(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "hf-dataset"
    stale_valid = output_dir / "valid.jsonl"
    stale_valid.parent.mkdir(parents=True, exist_ok=True)
    stale_valid.write_text("stale\n", encoding="utf-8")

    def fetcher(endpoint: str, params: dict[str, str]) -> dict[str, object]:
        if endpoint == "splits":
            return {
                "splits": [
                    {
                        "dataset": "HuggingFaceH4/ultrachat_200k",
                        "config": "default",
                        "split": "train_sft",
                    }
                ]
            }
        if endpoint == "rows":
            offset = params.get("offset", "0")
            if offset != "0":
                return {"rows": []}
            return {
                "rows": [
                    {
                        "row": {
                            "messages": [
                                {"role": "user", "content": "Say hi."},
                                {"role": "assistant", "content": "Hi."},
                            ]
                        }
                    },
                    {
                        "row": {
                            "messages": [
                                {"role": "user", "content": "Say bye."},
                                {"role": "assistant", "content": "Bye."},
                            ]
                        }
                    },
                ]
            }
        raise AssertionError(f"unexpected hf fetch: {endpoint} {params}")

    result = build_training_dataset_artifact(
        {
            "hf_dataset_path": "HuggingFaceH4/ultrachat_200k",
            "template": "source_schema",
            "dataset_id": "melix-hf-demo",
        },
        jobs_root=tmp_path / "jobs",
        output_dir=output_dir,
        source_model_id="melix-dev-text",
        hf_dataset_fetcher=fetcher,
    )

    payload = result.manifest_payload
    assert payload["source_kind"] == "hf_dataset"
    assert payload["hf_dataset_path"] == "HuggingFaceH4/ultrachat_200k"
    assert payload["hf_dataset_name"] == "default"
    assert payload["hf_train_split"] == "train"
    assert payload["source_manifest_path"].endswith("manifest.json")
    assert payload["source_samples_path"].endswith("samples.jsonl")
    assert payload["sample_count"] == 2
    assert stale_valid.exists() is False


def test_hf_preference_pair_schema_inference_and_mapping() -> None:
    default_reference = HFDatasetReference(
        dataset_path="melix/preferences",
        dataset_name="default",
        dataset_revision="main",
        train_split="train",
        chat_feature="",
        prompt_feature="",
        completion_feature="",
        text_feature="",
    )
    default_rows = [
        {
            "prompt": "Choose.",
            "chosen": "A.",
            "rejected": "B.",
        }
    ]
    assert training_dataset_module._infer_hf_dataset_format(
        default_reference,
        default_rows,
    ) == "preference_pair"
    assert training_dataset_module._map_hf_row_to_training_sample(
        default_rows[0],
        "preference_pair",
        default_reference,
    ) == {"prompt": "Choose.", "chosen": "A.", "rejected": "B."}

    configured_reference = HFDatasetReference(
        dataset_path="melix/preferences",
        dataset_name="default",
        dataset_revision="main",
        train_split="train",
        chat_feature="",
        prompt_feature="question",
        completion_feature="",
        text_feature="",
        chosen_feature="accepted",
        rejected_feature="rejected_answer",
    )
    configured_row = {
        "question": "Pick.",
        "accepted": "Use this.",
        "rejected_answer": "Avoid this.",
    }
    assert training_dataset_module._infer_hf_dataset_format(
        configured_reference,
        [configured_row],
    ) == "preference_pair"
    assert training_dataset_module._map_hf_row_to_training_sample(
        configured_row,
        "preference_pair",
        configured_reference,
    ) == {"prompt": "Pick.", "chosen": "Use this.", "rejected": "Avoid this."}

    with pytest.raises(ModelOperationError) as missing_column:
        training_dataset_module._map_hf_row_to_training_sample(
            {"question": "Pick.", "accepted": "Use this."},
            "preference_pair",
            configured_reference,
        )
    assert missing_column.value.code == "hf_dataset_fetch_failed"


def test_build_training_dataset_artifact_loads_existing_package_and_helper_branches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_package = tmp_path / "existing-package"
    _write_jsonl(
        source_package / "samples.jsonl",
        [
            {"text": "alpha beta"},
            {"text": "gamma delta"},
        ],
    )
    (source_package / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "existing-package",
                "format": "text_completion",
                "sample_count": 2,
                "version": "3",
                "validation_sample_count": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    built = build_training_dataset_artifact(
        {
            "dataset_uri": str(source_package),
            "template": "existing_package",
            "preview_count": "1",
        },
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "rebuilt-package",
        source_model_id="melix-dev-text",
    )

    assert built.manifest_payload["source_kind"] == "local_package"
    assert built.manifest_payload["conversion_template"] == "existing_package"
    assert built.manifest_payload["preview_samples"] == [{"text": "alpha beta"}]


    with pytest.raises(ModelOperationError) as missing_uri:
        training_dataset_module._resolve_dataset_build_source(
            {},
            jobs_root=tmp_path / "jobs",
            hf_dataset_fetcher=None,
            sample_limit=0,
        )
    assert missing_uri.value.code == "invalid_dataset_source"

    missing_path = tmp_path / "does-not-exist.jsonl"
    with pytest.raises(ModelOperationError) as missing_path_exc:
        training_dataset_module._resolve_dataset_build_source(
            {"dataset_uri": str(missing_path)},
            jobs_root=tmp_path / "jobs",
            hf_dataset_fetcher=None,
            sample_limit=0,
        )
    assert missing_path_exc.value.code == "invalid_dataset_source"

    invalid_jsonl = tmp_path / "invalid.jsonl"
    invalid_jsonl.write_text("{not-json}\n", encoding="utf-8")
    with pytest.raises(ModelOperationError) as invalid_json_exc:
        training_dataset_module._read_local_jsonl_rows(invalid_jsonl, sample_limit=0)
    assert invalid_json_exc.value.code == "invalid_dataset_source"

    scalar_jsonl = tmp_path / "scalar.jsonl"
    scalar_jsonl.write_text('"hello"\n', encoding="utf-8")
    with pytest.raises(ModelOperationError) as non_object_exc:
        training_dataset_module._read_local_jsonl_rows(scalar_jsonl, sample_limit=0)
    assert non_object_exc.value.code == "invalid_dataset_source"

    empty_jsonl = tmp_path / "empty.jsonl"
    empty_jsonl.write_text("\n\n", encoding="utf-8")
    with pytest.raises(ModelOperationError) as empty_exc:
        training_dataset_module._read_local_jsonl_rows(empty_jsonl, sample_limit=0)
    assert empty_exc.value.code == "invalid_dataset_source"

    assert training_dataset_module._resolve_local_conversion_template(
        "auto",
        {"instruction": "Do it", "output": "Done"},
    ) == "alpaca"
    assert training_dataset_module._resolve_local_conversion_template(
        "auto",
        {"prompt": "Choose", "chosen": "A", "rejected": "B"},
    ) == "preference_pair"
    assert training_dataset_module._resolve_local_conversion_template(
        "auto",
        {"conversation": []},
    ) == "sharegpt"
    with pytest.raises(ModelOperationError) as invalid_template:
        training_dataset_module._resolve_local_conversion_template("mystery", {"text": "hello"})
    assert invalid_template.value.code == "invalid_dataset_source"
    with pytest.raises(ModelOperationError) as no_template:
        training_dataset_module._resolve_local_conversion_template("auto", {"image": "unsupported"})
    assert no_template.value.code == "invalid_dataset_source"

    assert training_dataset_module._convert_local_rows(
        [{"text": "hello world"}],
        "text_completion",
    ) == ("text_completion", [{"text": "hello world"}])
    assert training_dataset_module._convert_local_rows(
        [{"prompt": "Choose", "chosen": "A", "rejected": "B"}],
        "preference_pair",
    ) == ("preference_pair", [{"prompt": "Choose", "chosen": "A", "rejected": "B"}])
    with pytest.raises(ModelOperationError) as bad_sharegpt_shape:
        training_dataset_module._convert_local_rows(
            [{"conversations": "bad"}],
            "sharegpt",
        )
    assert bad_sharegpt_shape.value.code == "invalid_dataset_source"
    with pytest.raises(ModelOperationError) as bad_sharegpt_turn:
        training_dataset_module._convert_local_rows(
            [{"conversations": ["bad-turn"]}],
            "sharegpt",
        )
    assert bad_sharegpt_turn.value.code == "invalid_dataset_source"
    with pytest.raises(ModelOperationError) as bad_sharegpt_role:
        training_dataset_module._convert_local_rows(
            [{"conversations": [{"from": "robot", "value": "??"}]}],
            "sharegpt",
        )
    assert bad_sharegpt_role.value.code == "invalid_dataset_source"
    with pytest.raises(ModelOperationError) as unsupported_template:
        training_dataset_module._convert_local_rows([{"text": "hello"}], "mystery")
    assert unsupported_template.value.code == "invalid_dataset_source"

    with pytest.raises(ModelOperationError) as split_exc:
        training_dataset_module._deterministic_validation_split([{"text": "solo"}], 0.5)
    assert split_exc.value.code == "invalid_dataset_source"

    split_samples = [
        {"prompt": f"prompt-{index}", "completion": f"completion-{index % 7}"}
        for index in range(40)
    ]
    full_sort_indices = {
        index
        for _, index in sorted(
            (
                training_dataset_module._canonical_sample_digest(sample),
                index,
            )
            for index, sample in enumerate(split_samples)
        )[:4]
    }
    nsmallest_calls = []
    real_nsmallest = training_dataset_module.heapq.nsmallest

    def counting_nsmallest(count, iterable):
        nsmallest_calls.append(count)
        return real_nsmallest(count, iterable)

    monkeypatch.setattr(training_dataset_module.heapq, "nsmallest", counting_nsmallest)
    train_split, validation_split = training_dataset_module._deterministic_validation_split(
        split_samples,
        0.1,
    )
    assert nsmallest_calls == [4]
    assert train_split == [
        sample for index, sample in enumerate(split_samples) if index not in full_sort_indices
    ]
    assert validation_split == [
        sample for index, sample in enumerate(split_samples) if index in full_sort_indices
    ]

    high_ratio_validation_indices = {
        index
        for _, index in sorted(
            (
                training_dataset_module._canonical_sample_digest(sample),
                index,
            )
            for index, sample in enumerate(split_samples)
        )[:36]
    }
    nlargest_calls = []
    real_nlargest = training_dataset_module.heapq.nlargest

    def counting_nlargest(count, iterable):
        nlargest_calls.append(count)
        return real_nlargest(count, iterable)

    monkeypatch.setattr(training_dataset_module.heapq, "nlargest", counting_nlargest)
    high_ratio_train_split, high_ratio_validation_split = training_dataset_module._deterministic_validation_split(
        split_samples,
        0.9,
    )
    assert nlargest_calls == [4]
    assert high_ratio_train_split == [
        sample for index, sample in enumerate(split_samples) if index not in high_ratio_validation_indices
    ]
    assert high_ratio_validation_split == [
        sample for index, sample in enumerate(split_samples) if index in high_ratio_validation_indices
    ]

    assert training_dataset_module._sample_token_counts({}, "chat_messages") == (0, 0)
    assert training_dataset_module._sample_token_counts(
        {"text": "hello world"},
        "text_completion",
    ) == (0, 2)
    sample_rows = [
        {"prompt": "hello world", "completion": "hello world"},
        {"prompt": "hello world", "completion": "hello world"},
    ]
    assert training_dataset_module._build_quality_report(sample_rows) == {
        "duplicate_count": 1,
        "duplicate_sample_indices": [1],
        "dirty_count": 2,
        "dirty_samples": [
            {"index": 0, "reasons": ["duplicate_prompt_completion"]},
            {"index": 1, "reasons": ["duplicate_prompt_completion"]},
        ],
    }
    assert training_dataset_module._build_token_stats(sample_rows, "prompt_completion") == {
        "estimator": "whitespace_v1",
        "sample_count": 2,
        "prompt_tokens_mean": 2.0,
        "prompt_tokens_p50": 2,
        "prompt_tokens_p95": 2,
        "prompt_tokens_max": 2,
        "completion_tokens_mean": 2.0,
        "completion_tokens_p50": 2,
        "completion_tokens_p95": 2,
        "completion_tokens_max": 2,
        "total_tokens_mean": 4.0,
        "total_tokens_p50": 4,
        "total_tokens_p95": 4,
        "total_tokens_max": 4,
    }
    assert training_dataset_module._mean_value([]) == 0.0
    assert training_dataset_module._percentile_value([], 0.95) == 0


def test_build_token_stats_reuses_single_sorted_pass_per_token_series(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_percentile_value(values: list[int], pct: float) -> int:
        raise AssertionError(f"legacy percentile helper should not run for optimized token stats ({pct=}, {values=})")

    def fail_generic_token_counter(sample: dict[str, object], format_name: str) -> tuple[int, int]:
        raise AssertionError(f"prompt_completion token stats should use the direct fast path ({format_name=})")

    def fail_mean_value(values: list[int]) -> float:
        raise AssertionError(f"prompt_completion token stats should reuse collected totals ({values=})")

    class SinglePassPromptCompletionSamples:
        def __init__(self) -> None:
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            if self.iterations > 1:
                raise AssertionError("prompt_completion token stats should consume the iterable only once")
            return iter(
                [
                    {"prompt": "a b c", "completion": "d e"},
                    {"prompt": "f", "completion": "g h i j"},
                    {"prompt": "k l", "completion": "m"},
                    {"prompt": "n o p q", "completion": "r s t"},
                ]
            )

    monkeypatch.setattr(training_dataset_module, "_percentile_value", fail_percentile_value)
    monkeypatch.setattr(training_dataset_module, "_sample_token_counts", fail_generic_token_counter)
    monkeypatch.setattr(training_dataset_module, "_mean_value", fail_mean_value)

    prompt_completion_samples = SinglePassPromptCompletionSamples()

    assert training_dataset_module._build_token_stats(
        prompt_completion_samples,
        "prompt_completion",
    ) == {
        "estimator": "whitespace_v1",
        "sample_count": 4,
        "prompt_tokens_mean": 2.5,
        "prompt_tokens_p50": 2,
        "prompt_tokens_p95": 3,
        "prompt_tokens_max": 4,
        "completion_tokens_mean": 2.5,
        "completion_tokens_p50": 2,
        "completion_tokens_p95": 3,
        "completion_tokens_max": 4,
        "total_tokens_mean": 5.0,
        "total_tokens_p50": 5,
        "total_tokens_p95": 5,
        "total_tokens_max": 7,
    }
    assert prompt_completion_samples.iterations == 1
    with pytest.raises(AssertionError, match="reuse collected totals"):
        fail_mean_value([])
    assert training_dataset_module._mean_value_from_total(0, 0) == 0.0

    monkeypatch.undo()
    assert training_dataset_module._build_token_stats(
        [
            {"text": "alpha beta gamma"},
            {"text": "delta"},
        ],
        "text_completion",
    ) == {
        "estimator": "whitespace_v1",
        "sample_count": 2,
        "prompt_tokens_mean": 0.0,
        "prompt_tokens_p50": 0,
        "prompt_tokens_p95": 0,
        "prompt_tokens_max": 0,
        "completion_tokens_mean": 2.0,
        "completion_tokens_p50": 1,
        "completion_tokens_p95": 1,
        "completion_tokens_max": 3,
        "total_tokens_mean": 2.0,
        "total_tokens_p50": 1,
        "total_tokens_p95": 1,
        "total_tokens_max": 3,
    }

    with pytest.raises(ModelOperationError) as int_parse_exc:
        training_dataset_module._int_ext_value(
            "bad",
            default=0,
            minimum=0,
            field_name="sample_limit",
        )
    assert int_parse_exc.value.code == "invalid_dataset_source"
    with pytest.raises(ModelOperationError) as int_range_exc:
        training_dataset_module._int_ext_value(
            "-1",
            default=0,
            minimum=0,
            field_name="sample_limit",
        )
    assert int_range_exc.value.code == "invalid_dataset_source"

    with pytest.raises(ModelOperationError) as float_parse_exc:
        training_dataset_module._float_ext_value(
            "bad",
            default=0.0,
            minimum=0.0,
            maximum=1.0,
            field_name="validation_ratio",
        )
    assert float_parse_exc.value.code == "invalid_dataset_source"
    with pytest.raises(ModelOperationError) as float_range_exc:
        training_dataset_module._float_ext_value(
            "1.5",
            default=0.0,
            minimum=0.0,
            maximum=1.0,
            field_name="validation_ratio",
        )
    assert float_range_exc.value.code == "invalid_dataset_source"


def test_build_token_stats_skips_quality_only_work(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_canonical_sample_digest(sample: dict[str, object]) -> bytes:
        raise AssertionError(f"token stats should not compute canonical digests ({sample=})")

    def fail_dirty_sample_reasons(sample: dict[str, object]) -> list[str]:
        raise AssertionError(f"token stats should not inspect dirty-sample reasons ({sample=})")

    monkeypatch.setattr(training_dataset_module, "_canonical_sample_digest", fail_canonical_sample_digest)
    monkeypatch.setattr(training_dataset_module, "_dirty_sample_reasons", fail_dirty_sample_reasons)

    assert training_dataset_module._build_token_stats(
        [
            {"prompt": "alpha beta", "completion": "gamma delta"},
            {"prompt": "epsilon", "completion": "zeta eta theta"},
        ],
        "prompt_completion",
    ) == {
        "estimator": "whitespace_v1",
        "sample_count": 2,
        "prompt_tokens_mean": 1.5,
        "prompt_tokens_p50": 1,
        "prompt_tokens_p95": 1,
        "prompt_tokens_max": 2,
        "completion_tokens_mean": 2.5,
        "completion_tokens_p50": 2,
        "completion_tokens_p95": 2,
        "completion_tokens_max": 3,
        "total_tokens_mean": 4.0,
        "total_tokens_p50": 4,
        "total_tokens_p95": 4,
        "total_tokens_max": 4,
    }


def test_build_quality_and_token_stats_caps_retained_examples_but_preserves_total_counts() -> None:
    repeated_sample = {"prompt": "same text", "completion": "same text"}

    quality, token_stats = training_dataset_module._build_quality_and_token_stats(
        [dict(repeated_sample) for _ in range(12)],
        "prompt_completion",
    )

    assert quality == {
        "duplicate_count": 11,
        "duplicate_sample_indices": list(range(1, 11)),
        "dirty_count": 12,
        "dirty_samples": [
            {"index": index, "reasons": ["duplicate_prompt_completion"]}
            for index in range(10)
        ],
    }
    assert token_stats["sample_count"] == 12
    assert token_stats["prompt_tokens_mean"] == 2.0
    assert token_stats["prompt_tokens_p95"] == 2
    assert token_stats["total_tokens_max"] == 4


def test_prompt_completion_dirty_sample_reasons_match_generic_quality_rules() -> None:
    samples = [
        {"prompt": "hello", "completion": "world"},
        {"prompt": "same text", "completion": " same text "},
        {"prompt": "bad\x00prompt", "completion": "clean"},
        {"prompt": "bad\x00same", "completion": "bad\x00same"},
    ]

    for sample in samples:
        assert training_dataset_module._prompt_completion_dirty_sample_reasons(
            sample
        ) == training_dataset_module._dirty_sample_reasons(sample)


def test_build_quality_and_token_stats_uses_prompt_completion_fast_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_generic_token_counter(sample: dict[str, object], format_name: str) -> tuple[int, int]:
        raise AssertionError(f"prompt_completion quality stats should use the direct fast path ({format_name=}, {sample=})")

    monkeypatch.setattr(training_dataset_module, "_sample_token_counts", fail_generic_token_counter)

    quality, token_stats = training_dataset_module._build_quality_and_token_stats(
        [
            {"prompt": "a b c", "completion": "d e"},
            {"prompt": "f", "completion": "g h i j"},
            {"prompt": "k l", "completion": "m"},
            {"prompt": "n o p q", "completion": "r s t"},
        ],
        "prompt_completion",
    )

    assert quality == {
        "duplicate_count": 0,
        "duplicate_sample_indices": [],
        "dirty_count": 0,
        "dirty_samples": [],
    }
    assert token_stats == {
        "estimator": "whitespace_v1",
        "sample_count": 4,
        "prompt_tokens_mean": 2.5,
        "prompt_tokens_p50": 2,
        "prompt_tokens_p95": 3,
        "prompt_tokens_max": 4,
        "completion_tokens_mean": 2.5,
        "completion_tokens_p50": 2,
        "completion_tokens_p95": 3,
        "completion_tokens_max": 4,
        "total_tokens_mean": 5.0,
        "total_tokens_p50": 5,
        "total_tokens_p95": 5,
        "total_tokens_max": 7,
    }

    monkeypatch.undo()
    assert training_dataset_module._build_quality_and_token_stats(
        [{"text": "alpha beta gamma"}, {"text": "delta"}],
        "text_completion",
    )[1] == {
        "estimator": "whitespace_v1",
        "sample_count": 2,
        "prompt_tokens_mean": 0.0,
        "prompt_tokens_p50": 0,
        "prompt_tokens_p95": 0,
        "prompt_tokens_max": 0,
        "completion_tokens_mean": 2.0,
        "completion_tokens_p50": 1,
        "completion_tokens_p95": 1,
        "completion_tokens_max": 3,
        "total_tokens_mean": 2.0,
        "total_tokens_p50": 1,
        "total_tokens_p95": 1,
        "total_tokens_max": 3,
    }


def test_build_quality_and_token_stats_uses_prompt_completion_duplicate_key_fast_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_generic_digest(sample: dict[str, object]) -> bytes:
        raise AssertionError(f"normalized prompt_completion samples should not hash JSON digests ({sample=})")

    monkeypatch.setattr(training_dataset_module, "_canonical_sample_digest", fail_generic_digest)

    quality, token_stats = training_dataset_module._build_quality_and_token_stats(
        [
            {"prompt": "same text", "completion": "answer"},
            {"prompt": "same text", "completion": "answer"},
            {"prompt": "different", "completion": "answer"},
        ],
        "prompt_completion",
    )

    assert quality == {
        "duplicate_count": 1,
        "duplicate_sample_indices": [1],
        "dirty_count": 0,
        "dirty_samples": [],
    }
    assert token_stats["sample_count"] == 3


def test_build_quality_and_token_stats_falls_back_to_generic_digest_for_non_normalized_prompt_completion_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digested_samples: list[dict[str, object]] = []
    original_digest = training_dataset_module._canonical_sample_digest

    def tracking_digest(sample: dict[str, object]) -> bytes:
        digested_samples.append(sample)
        return original_digest(sample)

    monkeypatch.setattr(training_dataset_module, "_canonical_sample_digest", tracking_digest)

    quality, token_stats = training_dataset_module._build_quality_and_token_stats(
        [
            {"prompt": "same text", "completion": "answer", "metadata": "a"},
            {"prompt": "same text", "completion": "answer", "metadata": "b"},
        ],
        "prompt_completion",
    )

    assert digested_samples == [
        {"prompt": "same text", "completion": "answer", "metadata": "a"},
        {"prompt": "same text", "completion": "answer", "metadata": "b"},
    ]
    assert quality == {
        "duplicate_count": 0,
        "duplicate_sample_indices": [],
        "dirty_count": 0,
        "dirty_samples": [],
    }
    assert token_stats["sample_count"] == 2


def test_summarize_token_values_preserves_input_order_by_default() -> None:
    values = [4, 1, 3, 2]

    summary = training_dataset_module._summarize_token_values(values, total=10)

    assert summary == {"mean": 2.5, "p50": 2, "p95": 3, "max": 4}
    assert values == [4, 1, 3, 2]


def test_summarize_token_values_can_sort_temporary_lists_in_place() -> None:
    values = [4, 1, 3, 2]

    summary = training_dataset_module._summarize_token_values(values, total=10, sort_in_place=True)

    assert summary == {"mean": 2.5, "p50": 2, "p95": 3, "max": 4}
    assert values == [1, 2, 3, 4]


def test_resolve_dataset_build_source_reuses_existing_package_sample_lists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalized_samples = [{"text": "alpha beta"}]
    normalized_validation_samples = [{"text": "gamma delta"}]
    package_path = tmp_path / "existing-package"
    package_path.mkdir(parents=True, exist_ok=True)
    package = TrainingDatasetPackage(
        package_path=package_path,
        manifest_path=package_path / "manifest.json",
        samples_path=package_path / "samples.jsonl",
        schema_version="melix.training_dataset_package.v1",
        dataset_id="existing-package",
        format="text_completion",
        sample_count=1,
        version="1",
        normalized_samples=normalized_samples,
        normalized_validation_samples=normalized_validation_samples,
        validation_sample_count=1,
        response_only_supported=False,
    )

    monkeypatch.setattr(
        training_dataset_module,
        "load_training_dataset_package",
        lambda dataset_uri, sample_limit=0: package,
    )

    resolved = training_dataset_module._resolve_dataset_build_source(
        {"dataset_uri": str(tmp_path / "existing-package"), "template": "existing_package"},
        jobs_root=tmp_path / "jobs",
        hf_dataset_fetcher=None,
        sample_limit=0,
    )

    assert resolved["samples"] is normalized_samples
    assert resolved["validation_samples"] is normalized_validation_samples


def test_resolve_dataset_build_source_reuses_hf_package_sample_lists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalized_samples = [
        {"messages": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]}
    ]
    normalized_validation_samples = [
        {"messages": [{"role": "user", "content": "Bye"}, {"role": "assistant", "content": "Goodbye"}]}
    ]
    package = TrainingDatasetPackage(
        package_path=tmp_path / "hf-package",
        manifest_path=tmp_path / "hf-package" / "manifest.json",
        samples_path=tmp_path / "hf-package" / "samples.jsonl",
        schema_version="melix.training_dataset_package.v1",
        dataset_id="hf-package",
        format="chat_messages",
        sample_count=1,
        version="1",
        normalized_samples=normalized_samples,
        normalized_validation_samples=normalized_validation_samples,
        validation_sample_count=1,
        response_only_supported=True,
    )
    reference = HFDatasetReference(
        dataset_path="HuggingFaceH4/ultrachat_200k",
        dataset_name="default",
        dataset_revision="main",
        train_split="train",
        valid_split="validation",
        chat_feature="messages",
        prompt_feature="",
        completion_feature="",
        text_feature="",
    )
    resolved_package = ResolvedTrainingDatasetPackage(
        package=package,
        source_kind="hf_dataset",
        dataset_uri="hf://HuggingFaceH4/ultrachat_200k",
        materialized_package_path=package.package_path,
        cache_key="demo-key",
        cache_hit=True,
        hf_reference=reference,
    )

    monkeypatch.setattr(
        training_dataset_module,
        "resolve_training_dataset_package",
        lambda request_ext, jobs_root, hf_dataset_fetcher, sample_limit=0: resolved_package,
    )

    resolved = training_dataset_module._resolve_dataset_build_source(
        {"hf_dataset_path": "HuggingFaceH4/ultrachat_200k", "template": "source_schema"},
        jobs_root=tmp_path / "jobs",
        hf_dataset_fetcher=None,
        sample_limit=0,
    )

    assert resolved["samples"] is normalized_samples
    assert resolved["validation_samples"] is normalized_validation_samples
    assert resolved["hf_metadata"]["hf_valid_split"] == "validation"


def test_build_training_dataset_artifact_inspects_samples_once_for_quality_and_token_stats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CountingSequence:
        def __init__(self, rows: list[dict[str, object]]) -> None:
            self._rows = rows
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            return iter(self._rows)

        def __len__(self) -> int:
            return len(self._rows)

        def __getitem__(self, index: int | slice) -> object:
            return self._rows[index]

        def __bool__(self) -> bool:
            return bool(self._rows)

    train_samples = CountingSequence(
        [
            {"prompt": "alpha beta", "completion": "gamma"},
            {"prompt": "delta", "completion": "delta"},
        ]
    )
    validation_samples = CountingSequence(
        [
            {"prompt": "alpha beta", "completion": "gamma"},
        ]
    )

    monkeypatch.setattr(
        training_dataset_module,
        "_resolve_dataset_build_source",
        lambda *args, **kwargs: {
            "dataset_id": "counted-source",
            "format": "prompt_completion",
            "version": "1",
            "source_kind": "local_path",
            "source_uri": "/tmp/counted-source.jsonl",
            "source_manifest_path": "",
            "source_samples_path": "/tmp/counted-source.jsonl",
            "samples": train_samples,
            "validation_samples": validation_samples,
            "response_only_supported": True,
            "conversion_template": "prompt_completion",
            "hf_metadata": {},
        },
    )

    built = build_training_dataset_artifact(
        {
            "inspect_only": "true",
            "preview_count": "2",
        },
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "inspect-once",
        source_model_id="melix-dev-text",
    )

    assert train_samples.iterations == 1
    assert validation_samples.iterations == 1
    assert built.manifest_payload["quality"] == {
        "duplicate_count": 1,
        "duplicate_sample_indices": [2],
        "dirty_count": 1,
        "dirty_samples": [
            {"index": 1, "reasons": ["duplicate_prompt_completion"]},
        ],
    }
    assert built.manifest_payload["token_stats"]["estimator"] == "whitespace_v1"
    assert built.manifest_payload["token_stats"]["sample_count"] == 3
    assert built.manifest_payload["token_stats"]["prompt_tokens_max"] == 2
    assert built.manifest_payload["token_stats"]["completion_tokens_max"] == 1
    assert built.manifest_payload["token_stats"]["total_tokens_max"] == 3



def test_build_training_dataset_artifact_streams_local_jsonl_without_bulk_row_helpers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_path = _write_jsonl(
        tmp_path / "alpaca-streamed.jsonl",
        [
            {
                "instruction": "Translate to French.",
                "input": "Hello world",
                "output": "Bonjour le monde",
            },
            {
                "instruction": "Summarize.",
                "input": "A short article",
                "output": "A concise summary",
            },
        ],
    )

    def fail_read_rows(path: Path, *, sample_limit: int) -> list[dict[str, object]]:
        raise AssertionError(f"bulk row reader should not be used for {path} ({sample_limit=})")

    def fail_convert_rows(rows: list[dict[str, object]], template: str) -> tuple[str, list[dict[str, object]]]:
        raise AssertionError(f"bulk row converter should not be used for {template}")

    monkeypatch.setattr(training_dataset_module, "_read_local_jsonl_rows", fail_read_rows)
    monkeypatch.setattr(training_dataset_module, "_convert_local_rows", fail_convert_rows)

    built = build_training_dataset_artifact(
        {
            "dataset_uri": str(dataset_path),
            "template": "auto",
            "preview_count": "1",
        },
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "streamed-package",
        source_model_id="melix-dev-text",
    )

    assert built.manifest_payload["source_kind"] == "local_path"
    assert built.manifest_payload["conversion_template"] == "alpaca"
    assert built.manifest_payload["sample_count"] == 2
    assert built.manifest_payload["preview_samples"] == [
        {
            "prompt": "Translate to French.\n\nInput:\nHello world",
            "completion": "Bonjour le monde",
        }
    ]
    assert (built.package_path / "samples.jsonl").read_text(encoding="utf-8") == (
        '{"prompt": "Translate to French.\\n\\nInput:\\nHello world", "completion": "Bonjour le monde"}\n'
        '{"prompt": "Summarize.\\n\\nInput:\\nA short article", "completion": "A concise summary"}\n'
    )


def test_local_jsonl_helpers_cover_streaming_and_single_row_conversions(tmp_path: Path) -> None:
    dataset_path = _write_jsonl(
        tmp_path / "helpers.jsonl",
        [
            {"messages": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]},
            {"prompt": "Question", "completion": "Answer"},
        ],
    )

    assert training_dataset_module._read_local_jsonl_rows(dataset_path, sample_limit=0) == [
        {"messages": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]},
        {"prompt": "Question", "completion": "Answer"},
    ]
    assert training_dataset_module._convert_local_row(
        {"messages": [{"role": "user", "content": "Hi"}]},
        "chat_messages",
    ) == {"messages": [{"role": "user", "content": "Hi"}]}
    assert training_dataset_module._convert_local_row(
        {"prompt": "Question", "completion": "Answer"},
        "prompt_completion",
    ) == {"prompt": "Question", "completion": "Answer"}

    empty_jsonl = tmp_path / "empty-stream.jsonl"
    empty_jsonl.write_text("\n", encoding="utf-8")
    with pytest.raises(ModelOperationError) as empty_exc:
        training_dataset_module._resolve_local_training_samples(
            empty_jsonl,
            template="auto",
            sample_limit=0,
        )
    assert empty_exc.value.code == "invalid_dataset_source"
