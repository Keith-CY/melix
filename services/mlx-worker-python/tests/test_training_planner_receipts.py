from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops import training_config as training_config_module
from worker.model_ops.errors import ModelOperationError
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline
from worker.model_ops.training_receipts import (
    eval_batch_size_receipt,
    expected_peak_memory_class,
    format_bound_value,
    grad_clip_policy_receipt,
    scheduler_kwargs_omitted_receipt,
    typed_validation_details,
)
from worker.model_ops.mlx_lm_runner import (
    MLXLMRunner,
    TrainingMetrics,
    TrainingRequest,
    TrainingResult,
)


_REQUIRED_RECEIPT_FIELDS = {
    "batching_strategy",
    "cutoff_len",
    "micro_batch_size",
    "effective_token_budget",
    "packing_mode",
    "media_counts",
    "kernel_policy",
    "expected_peak_memory_class",
    "profile_artifact_path",
    "compiled_step_enabled",
    "grad_checkpoint_enabled",
    "attention_backend",
    "metric_for_best_model_resolved",
    "generation_mode",
    "final_logit_softcapping",
}


def _text_model(**ext: str) -> common_pb2.ModelSpec:
    return common_pb2.ModelSpec(
        model_id="melix-dev-text",
        model_path="models/plain-llama",
        model_kind="text",
        revision="dev",
        max_context=4096,
        ext={"text_family_id": "llama", **ext},
    )


def _quantized_text_model(**ext: str) -> common_pb2.ModelSpec:
    model = _text_model(**ext)
    model.model_path = "models/qwen-q4"
    model.quant_profile_id = "q4"
    model.ext["melix.quantization.provider"] = "mlx"
    return model


def test_training_planner_receipt_covers_sft_batching_backend_and_numerical_policy() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(),
        ext={
            "training_mode": "lora",
            "batch_size": "3",
            "gradient_accumulation": "2",
            "max_seq_length": "1536",
            "packing_mode": "sample_packing",
            "media_image_count": "2",
            "media_audio_count": "1",
            "kernel_policy": "stable",
            "profile_artifact_path": ".runtime/profiles/train.json",
            "compiled_step": "true",
            "gradient_checkpointing": "true",
            "attention_backend": "sdpa",
            "metric_for_best_model": "eval_loss",
            "generation_mode": "disabled",
            "final_logit_softcapping": "30.0",
        },
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=5,
    )

    receipt = config.training_planner_receipt

    assert set(receipt) == _REQUIRED_RECEIPT_FIELDS
    assert receipt["batching_strategy"] == "micro_batch_accumulation"
    assert receipt["cutoff_len"] == 1536
    assert receipt["micro_batch_size"] == 3
    assert receipt["effective_token_budget"] == 3 * 2 * 1536
    assert receipt["packing_mode"] == "sample_packing"
    assert receipt["media_counts"] == {"audio": 1, "image": 2, "video": 0}
    assert receipt["kernel_policy"] == "stable"
    assert receipt["expected_peak_memory_class"] == "medium"
    assert receipt["profile_artifact_path"] == ".runtime/profiles/train.json"
    assert receipt["compiled_step_enabled"] is True
    assert receipt["grad_checkpoint_enabled"] is True
    assert receipt["attention_backend"] == {
        "backend": "sdpa",
        "status": "accepted",
        "reason": "",
    }
    assert receipt["metric_for_best_model_resolved"] == "eval_loss"
    assert receipt["generation_mode"] == "disabled"
    assert receipt["final_logit_softcapping"] == 30.0


def test_training_planner_receipt_covers_qlora_chunked_token_budget_and_refused_attention() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_quantized_text_model(),
        ext={
            "training_mode": "qlora",
            "batch_size": "1",
            "gradient_accumulation": "4",
            "max_seq_length": "4096",
            "chunked_training": "true",
            "chunk_size": "1024",
            "packing_mode": "none",
            "attention_backend": "flash_attention_2",
            "generation_mode": "teacher_forced",
            "final_logit_softcapping": "off",
        },
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )

    receipt = config.training_planner_receipt

    assert set(receipt) == _REQUIRED_RECEIPT_FIELDS
    assert receipt["batching_strategy"] == "chunked_micro_batch_accumulation"
    assert receipt["cutoff_len"] == 4096
    assert receipt["micro_batch_size"] == 1
    assert receipt["effective_token_budget"] == 1 * 4 * 1024
    assert receipt["packing_mode"] == "none"
    assert receipt["kernel_policy"] == "quantized_mlx"
    assert receipt["expected_peak_memory_class"] == "medium"
    assert receipt["compiled_step_enabled"] is False
    assert receipt["grad_checkpoint_enabled"] is True
    assert receipt["attention_backend"] == {
        "backend": "flash_attention_2",
        "status": "refused",
        "reason": "unsupported_training_attention_backend",
    }
    assert receipt["metric_for_best_model_resolved"] == "loss_best"
    assert receipt["generation_mode"] == "teacher_forced"
    assert receipt["final_logit_softcapping"] is None


def test_training_planner_receipt_rejects_unsafe_generation_mode() -> None:
    with pytest.raises(ModelOperationError) as exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(),
            ext={
                "training_mode": "lora",
                "generation_mode": "runtime_generate",
            },
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=2,
        )

    assert exc.value.code == "invalid_argument"
    assert exc.value.details == {
        "field": "generation_mode",
        "reason": "unsupported_generation_mode",
        "received": "runtime_generate",
        "supported_generation_modes": "disabled,teacher_forced",
    }


def test_training_planner_receipt_accepts_chunked_logits_softcap_alias() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(),
        ext={
            "training_mode": "lora",
            "chunked_logits_softcap": "18.5",
        },
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )

    assert config.training_planner_receipt["final_logit_softcapping"] == 18.5


def test_training_planner_receipt_accounts_for_source_model_size() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(**{"melix.parameter_count": "70000000000"}),
        ext={
            "training_mode": "lora",
            "batch_size": "1",
            "gradient_accumulation": "1",
            "max_seq_length": "512",
        },
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )

    assert config.training_planner_receipt["effective_token_budget"] == 512
    assert config.training_planner_receipt["expected_peak_memory_class"] == "high"


def test_training_planner_receipt_uses_resident_bytes_before_parameter_count() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_quantized_text_model(
            **{
                "melix.estimated_resident_bytes": str(9 * 1024 * 1024 * 1024),
                "melix.parameter_count": "3000000000",
            }
        ),
        ext={
            "training_mode": "lora",
            "batch_size": "1",
            "gradient_accumulation": "1",
            "max_seq_length": "512",
        },
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )

    assert config.training_planner_receipt["expected_peak_memory_class"] == "medium"


def test_training_planner_receipt_uses_medium_model_parameter_count() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(**{"parameter_count": "8000000000"}),
        ext={
            "training_mode": "lora",
            "batch_size": "1",
            "gradient_accumulation": "1",
            "max_seq_length": "512",
        },
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )

    assert config.training_planner_receipt["expected_peak_memory_class"] == "medium"


def test_training_planner_receipt_uses_model_size_aliases_and_ignores_malformed_values() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_quantized_text_model(
            **{
                "estimated_resident_bytes": "not-a-number",
                "resident_bytes": str(33 * 1024 * 1024 * 1024),
                "parameter_count": "bad",
                "parameters": "8000000000",
            }
        ),
        ext={
            "training_mode": "qlora",
            "batch_size": "1",
            "gradient_accumulation": "1",
            "max_seq_length": "512",
        },
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )

    assert config.training_planner_receipt["expected_peak_memory_class"] == "high"


def test_training_planner_receipt_classifies_high_token_budget_without_model_size() -> None:
    assert (
        expected_peak_memory_class(
            source_model=_text_model(),
            batch_size=3,
            gradient_accumulation=2,
            token_budget_unit=4096,
            training_mode="lora",
        )
        == "high"
    )


def test_training_receipt_helpers_cover_request_overrides() -> None:
    assert typed_validation_details(
        field_name="learning_rate",
        reason="below_minimum",
        received="-1.0",
        minimum=0.0,
        include_raw_value=True,
    ) == {
        "field": "learning_rate",
        "reason": "below_minimum",
        "received": "-1.0",
        "minimum": "0.0",
        "allowed_bounds": ">=0.0",
        "http_status": "422",
        "raw_value": "-1.0",
    }
    assert format_bound_value(2.25) == "2.25"
    assert grad_clip_policy_receipt(
        {"gradient_clip_norm": "0.75"},
        float_value=lambda raw, default, minimum, field_name: float(raw),
    ) == {
        "requested": "0.75",
        "resolved": 0.75,
        "enabled": True,
        "source": "request",
    }
    assert eval_batch_size_receipt(
        {"eval_batch_size": "4"},
        validation_sample_count=8,
        int_value=lambda raw, default, minimum, field_name: int(raw),
    ) == {
        "requested": "4",
        "resolved": 4,
        "source": "request",
        "validation_sample_count": 8,
    }
    assert scheduler_kwargs_omitted_receipt(
        {"scheduler_kwargs_json": '{"warmup": 5}', "scheduler": "cosine"}
    ) == {
        "omitted": True,
        "reason": "mlx_lm_lora_runner_does_not_accept_scheduler_kwargs",
        "keys": ["scheduler", "scheduler_kwargs_json"],
    }


def test_training_planner_receipt_is_persisted_in_adapter_manifest(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(tmp_path / "dataset")
    output_dir = tmp_path / "train-output"
    runner = _ReceiptRunner()

    result = LoRATrainingPipeline(runner=runner).run(
        job_id="planner-receipt-test",
        request_ext={
            "training_mode": "lora",
            "dataset_uri": str(dataset_dir),
            "batch_size": "1",
            "gradient_accumulation": "3",
            "max_seq_length": "1024",
            "profile_artifact_path": str(tmp_path / "profile.json"),
            "compiled_step": "true",
            "attention_backend": "mlx",
            "metric_for_best_model": "validation_loss",
            "generation_mode": "disabled",
            "final_logit_softcapping": "25.5",
        },
        source_model=_text_model(),
        output_dir=output_dir,
        jobs_root=tmp_path / "jobs",
    )

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert manifest == result.manifest
    for field in _REQUIRED_RECEIPT_FIELDS:
        assert manifest[field] == runner.last_train_request.config.training_planner_receipt[field]
    assert manifest["compiled_step_enabled"] is True
    assert manifest["attention_backend"]["status"] == "accepted"
    assert manifest["metric_for_best_model_resolved"] == "validation_loss"
    assert manifest["final_logit_softcapping"] == 25.5


def test_training_profiler_artifact_from_runner_metrics_is_linked_in_manifest(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(tmp_path / "dataset")
    output_dir = tmp_path / "train-output"
    runner = _ReceiptRunner(profile_artifact_path=tmp_path / "profiles" / "train-profile.json")

    result = LoRATrainingPipeline(runner=runner).run(
        job_id="planner-profiler-receipt-test",
        request_ext={
            "training_mode": "lora",
            "dataset_uri": str(dataset_dir),
            "metric_for_best_model": "loss_best",
        },
        source_model=_text_model(),
        output_dir=output_dir,
        jobs_root=tmp_path / "jobs",
    )

    assert result.manifest["profile_artifact_path"] == str(
        tmp_path / "profiles" / "train-profile.json"
    )
    assert result.manifest["metric_for_best_model_resolved"] == "loss_best"


class _ReceiptRunner(MLXLMRunner):
    def __init__(self, *, profile_artifact_path: Path | None = None) -> None:
        super().__init__()
        self.last_train_request: TrainingRequest | None = None
        self.profile_artifact_path = profile_artifact_path

    def train_native(self, request: TrainingRequest) -> TrainingResult:
        self.last_train_request = request
        request.adapter_output_dir.mkdir(parents=True, exist_ok=True)
        weights_path = request.adapter_output_dir / "adapters.safetensors"
        adapter_config_path = request.adapter_output_dir / "adapter_config.json"
        weights_path.write_bytes(b"melix-test-adapter")
        adapter_config_path.write_text("{}\n", encoding="utf-8")
        return TrainingResult(
            weights_path=weights_path,
            adapter_config_path=adapter_config_path,
            metrics=TrainingMetrics(
                job_duration_ms=123.0,
                tokens_seen=128,
                examples_seen=1,
                loss_final=0.4,
                loss_best=0.3,
                learning_rate_final=1e-4,
                tokens_per_second=64.0,
                peak_memory_gb=2.0,
                profile_artifact_path=(
                    str(self.profile_artifact_path) if self.profile_artifact_path else ""
                ),
            ),
            execution_backend="native",
        )


def _write_dataset_package(root: Path) -> Path:
    root.mkdir(parents=True)
    samples = [
        {
            "id": "sample-1",
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "world"},
            ],
        }
    ]
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "planner-receipt-fixture",
                "format": "chat_messages",
                "sample_count": len(samples),
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with (root / "samples.jsonl").open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample) + "\n")
    return root
