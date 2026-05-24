from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.errors import ModelOperationError
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline
from worker.model_ops.training_preflight import (
    TRAINABILITY_PREFLIGHT_SCHEMA_VERSION,
    TrainabilityPreflightResult,
    evaluate_trainability_preflight,
    require_trainability_preflight_ready,
)


def _text_model(
    *,
    model_id: str = "melix-test-gemma",
    model_path: str = "models/gemma-bf16",
    family_id: str = "gemma",
    max_context: int = 4096,
    quant_profile_id: str = "",
) -> common_pb2.ModelSpec:
    model = common_pb2.ModelSpec(
        model_id=model_id,
        model_path=model_path,
        model_kind="text",
        revision="main",
        max_context=max_context,
        quant_profile_id=quant_profile_id,
    )
    model.ext["text_family_id"] = family_id
    model.ext["text_layer_count"] = "2"
    return model


def _write_dataset_package(root: Path, *, sample_count: int = 2) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "messages": [
                {"role": "user", "content": f"prompt {index}"},
                {"role": "assistant", "content": f"completion {index}"},
            ]
        }
        for index in range(sample_count)
    ]
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "trainability-fixture",
                "format": "chat_messages",
                "sample_count": sample_count,
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "samples.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return root


def _blocked_codes(receipt: dict[str, object]) -> set[str]:
    return {
        str(check["code"])
        for check in receipt["checks"]  # type: ignore[index]
        if check["status"] == "blocked"
    }


def _operator_codes(receipt: dict[str, object]) -> list[str]:
    return [
        str(error["code"])
        for error in receipt["operator_errors"]  # type: ignore[index]
    ]


def test_trainability_preflight_ready_receipt_contains_schema_metrics_and_passed_checks() -> None:
    result = evaluate_trainability_preflight(
        source_model=_text_model(),
        request_ext={"training_mode": "lora"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
        validation_sample_count=1,
    )

    receipt = result.receipt

    assert result.config is not None
    assert receipt["schema_version"] == TRAINABILITY_PREFLIGHT_SCHEMA_VERSION
    assert receipt["status"] == "ready"
    assert receipt["model_id"] == "melix-test-gemma"
    assert receipt["model_family"] == "gemma"
    assert receipt["dataset_format"] == "chat_messages"
    assert receipt["training_mode"] == "lora"
    assert receipt["sample_count"] == 2
    assert receipt["validation_sample_count"] == 1
    assert receipt["operator_errors"] == []
    assert "unsupported_lora_target_module" not in _blocked_codes(receipt)
    assert receipt["metrics"]["sample_count"] == 2  # type: ignore[index]
    assert receipt["metrics"]["validation_sample_count"] == 1  # type: ignore[index]
    assert receipt["metrics"]["unsupported_configuration_count"] == 0  # type: ignore[index]
    assert "preflight_latency_ms" in receipt["metrics"]  # type: ignore[operator]
    assert "memory_estimate_latency_ms" in receipt["metrics"]  # type: ignore[operator]


def test_trainability_preflight_blocks_unsupported_lora_target_module() -> None:
    result = evaluate_trainability_preflight(
        source_model=_text_model(),
        request_ext={"target_modules": "rotary_emb"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
        validation_sample_count=0,
    )

    receipt = result.receipt

    assert result.config is None
    assert receipt["status"] == "blocked"
    assert "unsupported_lora_target_module" in _blocked_codes(receipt)
    assert _operator_codes(receipt) == ["unsupported_lora_target_module"]
    assert receipt["operator_errors"][0]["details"]["target_module"] == "rotary_emb"  # type: ignore[index]


def test_trainability_preflight_blocks_insufficient_training_samples_for_supported_sft_config() -> None:
    result = evaluate_trainability_preflight(
        source_model=_text_model(),
        request_ext={},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=0,
        validation_sample_count=0,
    )

    receipt = result.receipt

    assert receipt["status"] == "blocked"
    assert "insufficient_training_samples" in _blocked_codes(receipt)
    assert _operator_codes(receipt)[0] == "insufficient_training_samples"


def test_trainability_preflight_allows_non_sft_contracts_to_keep_existing_dataset_validation() -> None:
    result = evaluate_trainability_preflight(
        source_model=_text_model(),
        request_ext={
            "training_mode": "rlhf",
            "reward_model_manifest_path": "reward-model.json",
        },
        dataset_format="reward_scored",
        response_only_supported=False,
        sample_count=0,
        validation_sample_count=0,
    )

    receipt = result.receipt

    assert receipt["status"] == "ready"
    assert result.config is not None
    assert result.config.dataset_contract == "reward_scored"


def test_require_trainability_preflight_ready_rejects_ready_receipt_without_config(tmp_path: Path) -> None:
    receipt_path = tmp_path / "trainability-preflight.json"
    result = TrainabilityPreflightResult(
        receipt={
            "schema_version": TRAINABILITY_PREFLIGHT_SCHEMA_VERSION,
            "status": "ready",
            "operator_errors": [],
        },
        config=None,
    )

    with pytest.raises(ModelOperationError) as exc:
        require_trainability_preflight_ready(result=result, receipt_path=receipt_path)

    assert exc.value.code == "trainability_preflight_invalid"
    assert exc.value.details["trainability_preflight_receipt_path"] == str(receipt_path)


def test_trainability_preflight_blocks_sequence_length_that_exceeds_model_context() -> None:
    result = evaluate_trainability_preflight(
        source_model=_text_model(max_context=4096),
        request_ext={"max_seq_length": "8192"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
        validation_sample_count=0,
    )

    receipt = result.receipt

    assert receipt["status"] == "blocked"
    assert "sequence_length_exceeds_model_context" in _blocked_codes(receipt)
    assert _operator_codes(receipt)[0] == "sequence_length_exceeds_model_context"
    assert receipt["operator_errors"][0]["details"]["max_context"] == "4096"  # type: ignore[index]


def test_trainability_preflight_blocks_memory_fit_failure_when_risk_not_allowed() -> None:
    result = evaluate_trainability_preflight(
        source_model=_text_model(),
        request_ext={
            "estimated_training_memory_gb": "80",
            "available_memory_gb": "64",
        },
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
        validation_sample_count=0,
    )

    receipt = result.receipt

    assert receipt["status"] == "blocked"
    assert "training_memory_fit_failed" in _blocked_codes(receipt)
    assert _operator_codes(receipt)[0] == "training_memory_fit_failed"
    assert receipt["operator_errors"][0]["details"]["estimated_training_memory_gb"] == "80.000"  # type: ignore[index]
    assert receipt["operator_errors"][0]["details"]["available_memory_gb"] == "64.000"  # type: ignore[index]


def test_trainability_preflight_blocks_quantized_embedding_targets_with_operator_remediation() -> None:
    result = evaluate_trainability_preflight(
        source_model=_text_model(
            model_path="mlx-community/gemma-MLX-8bit",
            quant_profile_id="8bit",
        ),
        request_ext={"training_mode": "qlora", "target_modules": "embed_tokens"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
        validation_sample_count=0,
    )

    receipt = result.receipt

    assert receipt["status"] == "blocked"
    assert "unsafe_quantized_lora_target" in _blocked_codes(receipt)
    assert _operator_codes(receipt) == ["unsafe_quantized_lora_target"]
    assert (
        receipt["operator_errors"][0]["remediation"]  # type: ignore[index]
        == "Choose non-embedding LoRA target modules for quantized base models."
    )
    assert receipt["operator_errors"][0]["details"]["unsupported_target_class"] == "embedding_or_head"  # type: ignore[index]


def test_trainability_preflight_blocks_quantized_full_finetuning_with_operator_remediation() -> None:
    result = evaluate_trainability_preflight(
        source_model=_text_model(
            model_path="mlx-community/gemma-MLX-8bit",
            quant_profile_id="8bit",
        ),
        request_ext={"training_mode": "full_finetune"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
        validation_sample_count=0,
    )

    receipt = result.receipt

    assert result.config is None
    assert receipt["status"] == "blocked"
    assert "unsupported_full_finetune_quantized_base" in _blocked_codes(receipt)
    assert _operator_codes(receipt) == ["unsupported_full_finetune_quantized_base"]
    assert (
        receipt["operator_errors"][0]["remediation"]  # type: ignore[index]
        == "Use LoRA or QLoRA for quantized bases, or switch to an unquantized base model."
    )
    assert receipt["operator_errors"][0]["details"]["training_mode"] == "full_finetune"  # type: ignore[index]


def test_trainability_preflight_classifies_training_mode_family_and_dataset_errors() -> None:
    unsupported_mode = evaluate_trainability_preflight(
        source_model=_text_model(),
        request_ext={"training_mode": "full_finetune"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
        validation_sample_count=0,
    ).receipt
    unsupported_family = evaluate_trainability_preflight(
        source_model=_text_model(family_id="deepseek-mla"),
        request_ext={},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
        validation_sample_count=0,
    ).receipt
    invalid_dataset = evaluate_trainability_preflight(
        source_model=_text_model(),
        request_ext={},
        dataset_format="image_pairs",
        response_only_supported=False,
        sample_count=2,
        validation_sample_count=0,
    ).receipt

    assert _operator_codes(unsupported_mode) == ["unsupported_training_mode"]
    assert _operator_codes(unsupported_family) == ["unsupported_model_family"]
    assert _operator_codes(invalid_dataset) == ["invalid_dataset_package"]


def test_lora_training_pipeline_writes_blocked_preflight_receipt_and_does_not_call_runner(
    tmp_path: Path,
) -> None:
    class NoLaunchRunner:
        def __init__(self) -> None:
            self.train_called = False

        def train(self, request):  # noqa: ANN001
            self.train_called = True
            raise AssertionError("runner.train should not be called after blocked preflight")

    dataset_dir = _write_dataset_package(tmp_path / "dataset")
    output_dir = tmp_path / "output"
    runner = NoLaunchRunner()

    with pytest.raises(ModelOperationError) as exc:
        LoRATrainingPipeline(runner=runner).run(
            job_id="train-blocked-preflight",
            request_ext={
                "operation": "train_lora",
                "adapter_name": "blocked-target",
                "dataset_uri": str(dataset_dir),
                "target_modules": "rotary_emb",
            },
            source_model=_text_model(),
            output_dir=output_dir,
            jobs_root=tmp_path / "jobs",
        )

    receipt_path = output_dir / "trainability-preflight.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert exc.value.code == "unsupported_lora_target_module"
    assert runner.train_called is False
    assert receipt["schema_version"] == TRAINABILITY_PREFLIGHT_SCHEMA_VERSION
    assert receipt["status"] == "blocked"
    assert _operator_codes(receipt) == ["unsupported_lora_target_module"]
    assert exc.value.details["trainability_preflight_receipt_path"] == str(receipt_path)
    assert not (output_dir / "train_lora.adapter.json").exists()
