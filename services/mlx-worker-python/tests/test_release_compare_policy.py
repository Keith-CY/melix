from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops import training_config as training_config_module
from worker.model_ops.deterministic_lora_runner import DeterministicLoRARunner
from worker.model_ops.errors import ModelOperationError
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline
from worker.model_ops.release_compare_policy import ReleaseCompareBundlePolicy


def _write_dataset_package(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "melix-dev-dataset",
                "format": "chat_messages",
                "sample_count": 1,
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "samples.jsonl").write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "world"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return root


def _text_model(*, family_id: str = "qwen") -> common_pb2.ModelSpec:
    model = common_pb2.ModelSpec(
        model_id="melix-test-text",
        model_path="models/plain-qwen",
        model_kind="text",
        revision="main",
        max_context=4096,
    )
    model.ext["text_family_id"] = family_id
    model.ext["text_layer_count"] = "2"
    return model


def test_normalize_training_config_records_release_compare_bundle_policy() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(),
        ext={
            "release_compare_in_domain_suite_ids": "opensearch_vl_qa, opensearch_vl_qa, opensearch_vl_grounding",
            "release_compare_guard_suite_ids": "mmlu, gsm8k",
            "release_compare_thresholds": "opensearch_vl_qa=0.04,mmlu=0.0",
            "release_compare_default_threshold": "0.02",
            "release_compare_minimum_sample_counts": "opensearch_vl_qa=64",
            "release_compare_default_minimum_sample_count": "32",
        },
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )

    policy = config.release_compare_bundle_policy
    assert policy.in_domain_suite_ids == [
        "opensearch_vl_qa",
        "opensearch_vl_grounding",
    ]
    assert policy.guard_suite_ids == ["mmlu", "gsm8k"]
    assert policy.thresholds == {
        "opensearch_vl_qa": 0.04,
        "opensearch_vl_grounding": 0.02,
        "mmlu": 0.0,
        "gsm8k": 0.02,
    }
    assert policy.minimum_sample_counts == {
        "opensearch_vl_qa": 64,
        "opensearch_vl_grounding": 32,
        "mmlu": 32,
        "gsm8k": 32,
    }


def test_normalize_training_config_accepts_namespaced_release_compare_keys() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(),
        ext={
            "melix.release_compare.in_domain_suite_ids": "opensearch_vl_qa",
            "melix.release_compare.guard_suite_ids": "mmlu",
            "melix.release_compare.thresholds": "opensearch_vl_qa=0.03",
            "melix.release_compare.default_threshold": "0.01",
            "melix.release_compare.minimum_sample_counts": "mmlu=48",
            "melix.release_compare.default_minimum_sample_count": "24",
        },
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )

    policy = config.release_compare_bundle_policy
    assert policy.in_domain_suite_ids == ["opensearch_vl_qa"]
    assert policy.guard_suite_ids == ["mmlu"]
    assert policy.thresholds == {"opensearch_vl_qa": 0.03, "mmlu": 0.01}
    assert policy.minimum_sample_counts == {
        "opensearch_vl_qa": 24,
        "mmlu": 48,
    }


def test_normalize_training_config_rejects_invalid_release_compare_policy() -> None:
    with pytest.raises(ModelOperationError) as threshold_exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(),
            ext={
                "release_compare_in_domain_suite_ids": "opensearch_vl_qa",
                "release_compare_thresholds": "opensearch_vl_qa=-0.01",
            },
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )
    assert threshold_exc.value.code == "invalid_argument"
    assert threshold_exc.value.details["field"] == (
        "release_compare_thresholds.opensearch_vl_qa"
    )

    with pytest.raises(ModelOperationError) as sample_count_exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(),
            ext={
                "release_compare_guard_suite_ids": "mmlu",
                "release_compare_minimum_sample_counts": "mmlu=0",
            },
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )
    assert sample_count_exc.value.code == "invalid_argument"
    assert sample_count_exc.value.details["field"] == (
        "release_compare_minimum_sample_counts.mmlu"
    )


def test_release_compare_policy_rejects_malformed_keyed_entries() -> None:
    with pytest.raises(ModelOperationError) as exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(),
            ext={
                "release_compare_in_domain_suite_ids": "opensearch_vl_qa",
                "release_compare_thresholds": "opensearch_vl_qa",
            },
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )

    assert exc.value.code == "invalid_argument"
    assert exc.value.details == {
        "field": "release_compare_thresholds",
        "raw_value": "opensearch_vl_qa",
    }


def test_release_compare_policy_manifest_has_schema_version() -> None:
    policy = ReleaseCompareBundlePolicy(
        in_domain_suite_ids=["opensearch_vl_qa"],
        guard_suite_ids=["mmlu"],
        thresholds={"opensearch_vl_qa": 0.04, "mmlu": 0.01},
        minimum_sample_counts={"opensearch_vl_qa": 64, "mmlu": 32},
    )

    assert policy.as_manifest() == {
        "schema_version": "melix.lora_release_compare_bundle_policy.v1",
        "in_domain_suite_ids": ["opensearch_vl_qa"],
        "guard_suite_ids": ["mmlu"],
        "thresholds": {"opensearch_vl_qa": 0.04, "mmlu": 0.01},
        "minimum_sample_counts": {"opensearch_vl_qa": 64, "mmlu": 32},
    }


def test_lora_training_manifest_records_release_compare_bundle_policy(
    tmp_path: Path,
) -> None:
    dataset_dir = _write_dataset_package(tmp_path / "dataset")

    result = LoRATrainingPipeline(runner=DeterministicLoRARunner()).run(
        job_id="train-release-compare-policy",
        request_ext={
            "operation": "train_lora",
            "adapter_name": "opensearch-vl-adapter",
            "dataset_uri": str(dataset_dir),
            "release_compare_in_domain_suite_ids": "opensearch_vl_qa",
            "release_compare_guard_suite_ids": "mmlu,gsm8k",
            "release_compare_thresholds": "opensearch_vl_qa=0.05",
            "release_compare_default_threshold": "0.01",
            "release_compare_minimum_sample_counts": "opensearch_vl_qa=80",
            "release_compare_default_minimum_sample_count": "40",
        },
        source_model=_text_model(),
        output_dir=tmp_path / "output",
        jobs_root=tmp_path / "jobs",
    )

    manifest_payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    expected_thresholds = {
        "opensearch_vl_qa": 0.05,
        "mmlu": 0.01,
        "gsm8k": 0.01,
    }
    expected_sample_counts = {
        "opensearch_vl_qa": 80,
        "mmlu": 40,
        "gsm8k": 40,
    }
    assert manifest_payload["release_compare_bundle_policy"] == {
        "schema_version": "melix.lora_release_compare_bundle_policy.v1",
        "in_domain_suite_ids": ["opensearch_vl_qa"],
        "guard_suite_ids": ["mmlu", "gsm8k"],
        "thresholds": expected_thresholds,
        "minimum_sample_counts": expected_sample_counts,
    }
    assert manifest_payload["release_compare_in_domain_suite_ids"] == [
        "opensearch_vl_qa"
    ]
    assert manifest_payload["release_compare_guard_suite_ids"] == ["mmlu", "gsm8k"]
    assert manifest_payload["release_compare_thresholds"] == expected_thresholds
    assert manifest_payload["release_compare_minimum_sample_counts"] == (
        expected_sample_counts
    )
