from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import types

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops import adapter_activation_pipeline as adapter_activation_pipeline_module
from worker.model_ops.deterministic_lora_runner import DeterministicLoRARunner
from worker.model_ops.errors import ModelOperationError
from worker.model_ops import mlx_lm_runner as mlx_lm_runner_module
from worker.model_ops import training_config as training_config_module
from worker.model_ops import training_dataset as training_dataset_module
from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.lora_training_pipeline import (
    LoRATrainingPipeline,
    _content_hash,
    _int_ext,
    _latest_checkpoint_from_directory,
    _load_manifest_payload,
    _resolve_resume_context,
    _resolve_resume_path_from_manifest,
    _resolve_adapter_scope_metadata,
    _validated_resume_path,
)
from worker.model_ops.lora_runtime_metadata import build_adapter_runtime_manifest_fields
from worker.model_ops.lora_runtime_metadata import build_lora_canary_receipt_fields
from worker.model_ops.lora_runtime_metadata import build_quantized_lora_manifest_fields
from worker.model_ops.multimodal_lora_contracts import (
    _adapter_parameter_matches_fragment,
    audit_adapter_checkpoint,
    finite_masked_softmax,
)
from worker.model_ops.mlx_lm_runner import MLXLMRunner
from worker.model_ops.mlx_lm_runner import TrainingMetrics, TrainingRequest, TrainingResult
from worker.model_ops.training_dataset import (
    HFDatasetReference,
    load_training_dataset_package,
    materialize_hf_training_dataset_package,
)
from worker.runtime.mlx_text_runtime import MLXTextRuntime, RuntimeTokenEvent, RuntimeUnavailableError


def _write_dataset_package(
    root: Path,
    *,
    manifest_payload: dict[str, object] | None = None,
    sample_lines: list[str] | None = None,
    valid_lines: list[str] | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    manifest = manifest_payload or {
        "schema_version": "melix.training_dataset_package.v1",
        "dataset_id": "melix-dev-dataset",
        "format": "chat_messages",
        "sample_count": 1,
        "version": "1",
    }
    (root / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    lines = sample_lines or [
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "world"},
                ]
            }
        )
    ]
    (root / "samples.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if valid_lines is not None:
        (root / "valid.jsonl").write_text("\n".join(valid_lines) + "\n", encoding="utf-8")
    return root


def _text_model(*, model_path: str = "models/plain-llama", quant_profile_id: str = "", family_id: str = "") -> common_pb2.ModelSpec:
    model = common_pb2.ModelSpec(
        model_id="melix-test-text",
        model_path=model_path,
        model_kind="text",
        revision="main",
        quant_profile_id=quant_profile_id,
        max_context=4096,
    )
    if family_id:
        model.ext["text_family_id"] = family_id
    model.ext["text_layer_count"] = "2"
    return model


def _gemma4_vlm_model(*, model_path: str = "models/gemma-4-E4B-it-bf16") -> common_pb2.ModelSpec:
    model = common_pb2.ModelSpec(
        model_id="melix-gemma4-vlm",
        model_path=model_path,
        model_kind="vlm",
        revision="main",
        max_context=8192,
    )
    model.ext["melix.lora.family_id"] = "gemma"
    model.ext["melix.lora.family_kind"] = "dense"
    model.ext["melix.lora.support_tier"] = "stable"
    model.ext["melix.lora.training_ready"] = "true"
    model.ext["melix.lora.default_target_preset"] = "attention_mlp"
    model.ext["melix.lora.adapter_scope"] = "text_backbone"
    model.ext["melix.lora.training_surface"] = "text_backbone"
    model.ext["melix.lora.base_model_path"] = model_path
    model.ext["melix.lora.component_model_type"] = "gemma4_text"
    model.ext["melix.component.text_backbone.model_type"] = "gemma4_text"
    model.ext["melix.component.text_backbone.family_id"] = "gemma"
    model.ext["melix.component.text_backbone.lora_supported"] = "true"
    model.ext["melix.component.text_backbone.training_ready"] = "true"
    return model


def test_lora_training_pipeline_uses_component_scope_metadata_for_gemma4_vlm(tmp_path: Path) -> None:
    class RecordingRunner(DeterministicLoRARunner):
        def __init__(self) -> None:
            super().__init__()
            self.last_request = None

        def train_native(self, request):  # noqa: ANN001
            self.last_request = request
            return super().train_native(request)

    component_model_dir = tmp_path / "gemma4-vlm"
    component_model_dir.mkdir()
    dataset_dir = _write_dataset_package(tmp_path / "dataset")
    runner = RecordingRunner()

    result = LoRATrainingPipeline(runner=runner).run(
        job_id="train-gemma4-vlm",
        request_ext={
            "operation": "train_lora",
            "adapter_name": "gemma4-text-backbone",
            "dataset_uri": str(dataset_dir),
        },
        source_model=_gemma4_vlm_model(model_path=str(component_model_dir)),
        output_dir=tmp_path / "output",
        jobs_root=tmp_path / "jobs",
    )

    assert runner.last_request is not None
    assert runner.last_request.model_path == component_model_dir
    assert runner.last_request.source_model_kind == "vlm"
    assert runner.last_request.source_model_ext["melix.lora.adapter_scope"] == "text_backbone"
    assert result.manifest["source_model_kind"] == "vlm"
    assert result.manifest["adapter_scope"] == "text_backbone"
    assert result.manifest["training_surface"] == "text_backbone"
    assert result.manifest["component_model_type"] == "gemma4_text"
    assert result.manifest["component_family"] == "gemma"
    assert result.manifest["component_model_path"] == str(component_model_dir)
    assert result.manifest["multimodal_lora_nan_guard_triggered"] is False
    assert result.manifest["unexpected_frozen_param_count"] == 0
    assert result.manifest["adapter_checkpoint_bytes"] == result.manifest["adapter_artifact_bytes"]
    assert result.manifest["training.multimodal_lora_nan_guard_triggered"] is False
    assert result.manifest["training.unexpected_frozen_param_count"] == 0


def test_lora_training_manifest_records_quantized_qlora_compatibility_for_gemma8bit(
    tmp_path: Path,
) -> None:
    dataset_dir = _write_dataset_package(tmp_path / "dataset")

    result = LoRATrainingPipeline(runner=DeterministicLoRARunner()).run(
        job_id="train-gemma8bit-qlora",
        request_ext={
            "operation": "train_lora",
            "training_mode": "qlora",
            "adapter_name": "gemma8bit-dialogue-adapter",
            "dataset_uri": str(dataset_dir),
        },
        source_model=_text_model(
            model_path="unsloth/gemma-4-E4B-it-MLX-8bit",
            family_id="gemma",
        ),
        output_dir=tmp_path / "output",
        jobs_root=tmp_path / "jobs",
    )

    assert result.manifest["training_mode"] == "qlora"
    assert result.manifest["quantization_mode"] == "quantized_base"
    assert result.manifest["quantized_base_detected"] is True
    assert result.manifest["quantized_base_kind"] == "8bit"
    assert result.manifest["quantization_profile_id"] == ""
    assert result.manifest["quantized_base_evidence_source"] == "model_identity"
    assert result.manifest["qlora_compatibility_status"] == "compatible"
    assert result.manifest["quantized_target_module_guard"] == "accepted"
    assert result.manifest["training.adapter_checkpoint_bytes"] == result.manifest["adapter_checkpoint_bytes"]
    freeze_audit = result.manifest["adapter_freeze_audit"]
    assert freeze_audit["unexpected_serialized_param_count"] == 0
    assert freeze_audit["unexpected_trainable_param_count"] == 0
    assert freeze_audit["adapter_checkpoint_size_within_target"] is True


def test_lora_training_manifest_records_canary_receipts(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(tmp_path / "dataset")
    base_model_dir = tmp_path / "base-model"
    base_model_dir.mkdir()
    (base_model_dir / "config.json").write_text('{"model_type":"qwen2"}\n', encoding="utf-8")
    (base_model_dir / "tokenizer_config.json").write_text(
        json.dumps({"eos_token": "<|endoftext|>"}) + "\n",
        encoding="utf-8",
    )
    (base_model_dir / "processor_config.json").write_text('{"processor_class":"AutoProcessor"}\n', encoding="utf-8")
    (base_model_dir / "modeling_qwen2.py").write_text("# custom module\n", encoding="utf-8")

    result = LoRATrainingPipeline(runner=DeterministicLoRARunner()).run(
        job_id="train-canary-receipts",
        request_ext={
            "operation": "train_lora",
            "adapter_name": "canary-adapter",
            "dataset_uri": str(dataset_dir),
        },
        source_model=_text_model(model_path=str(base_model_dir), family_id="qwen"),
        output_dir=tmp_path / "output",
        jobs_root=tmp_path / "jobs",
    )

    assert result.manifest["source_eos_token"] == "<|endoftext|>"
    assert result.manifest["saved_eos_token"] == "<|endoftext|>"
    assert result.manifest["tokenizer_config_path"] == str(base_model_dir / "tokenizer_config.json")
    assert result.manifest["base_config_present"] is True
    assert result.manifest["processor_resume_mode"] == "processor_config"
    assert result.manifest["aux_modules_restored"] is True
    assert result.manifest["merge_export_canary_result"] == "pass"
    assert result.manifest["callback_api_drift_result"] == "pass"
    assert result.manifest["completion_loss"] == 0.42
    assert result.manifest["round_trip_passed"] is True
    assert result.manifest["grad_norm"] == 0.0


def test_quantized_lora_metadata_does_not_treat_fp_profile_as_quantized() -> None:
    source_model = _text_model(
        model_path="mlx-community/plain-gemma-bf16",
        quant_profile_id="bf16",
        family_id="gemma",
    )

    fields = build_quantized_lora_manifest_fields(
        source_model=source_model,
        training_mode="lora",
        quantization_mode="none",
        target_modules=["model.layers.0.self_attn.q_proj"],
    )

    assert fields["quantized_base_detected"] is False
    assert fields["quantized_base_kind"] == "unknown"
    assert fields["quantization_profile_id"] == "bf16"
    assert fields["quantized_base_evidence_source"] == ""
    assert fields["qlora_compatibility_status"] == "not_applicable"
    assert fields["quantized_target_module_guard"] == "not_required"


def test_lora_canary_receipt_records_tokenizer_resume_and_drift_status(
    tmp_path: Path,
) -> None:
    base_model_dir = tmp_path / "base-model"
    base_model_dir.mkdir()
    (base_model_dir / "config.json").write_text('{"model_type":"qwen2"}\n', encoding="utf-8")
    (base_model_dir / "tokenizer_config.json").write_text(
        json.dumps({"eos_token": "<|source-eos|>"}) + "\n",
        encoding="utf-8",
    )
    (base_model_dir / "tokenizer.json").write_text(
        json.dumps({"model": {}, "added_tokens": [{"content": "<|source-eos|>", "special": True}]})
        + "\n",
        encoding="utf-8",
    )
    (base_model_dir / "processor_config.json").write_text('{"processor_class":"AutoProcessor"}\n', encoding="utf-8")
    (base_model_dir / "modeling_qwen2.py").write_text("# custom module\n", encoding="utf-8")

    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    adapter_config_path = adapter_dir / "adapter_config.json"
    adapter_config_path.write_text(
        json.dumps(
            {
                "tokenizer_config": {"eos_token": "<|source-eos|>"},
                "completion_loss": 0.125,
                "grad_norm": 0.75,
                "round_trip_passed": True,
                "callback_arity": 2,
                "expected_callback_arity": 2,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    weights_path = adapter_dir / "adapters.safetensors"
    weights_path.write_bytes(b"adapter")

    fields = build_lora_canary_receipt_fields(
        source_model=_text_model(model_path=str(base_model_dir)),
        adapter_output_dir=adapter_dir,
        adapter_config_path=adapter_config_path,
        weights_path=weights_path,
        training_metrics=TrainingMetrics(
            job_duration_ms=1.0,
            tokens_seen=8,
            examples_seen=1,
            loss_final=0.125,
            loss_best=0.125,
            learning_rate_final=1e-5,
            grad_norm=0.75,
            completion_loss=0.125,
            round_trip_passed=True,
        ),
    )

    assert fields["source_eos_token"] == "<|source-eos|>"
    assert fields["saved_eos_token"] == "<|source-eos|>"
    assert fields["tokenizer_config_path"] == str(base_model_dir / "tokenizer_config.json")
    assert fields["base_config_present"] is True
    assert fields["processor_resume_mode"] == "processor_config"
    assert fields["aux_modules_restored"] is True
    assert fields["merge_export_canary_result"] == "pass"
    assert fields["callback_api_drift_result"] == "pass"
    assert fields["completion_loss"] == 0.125
    assert fields["round_trip_passed"] is True
    assert fields["grad_norm"] == 0.75


def test_lora_canary_receipt_detects_missing_checkpoint_resume_assets(
    tmp_path: Path,
) -> None:
    base_model_dir = tmp_path / "base-model"
    base_model_dir.mkdir()
    (base_model_dir / "config.json").write_text('{"model_type":"qwen2"}\n', encoding="utf-8")
    (base_model_dir / "tokenizer_config.json").write_text(
        json.dumps({"model_max_length": 8192}) + "\n",
        encoding="utf-8",
    )
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    adapter_config_path = adapter_dir / "adapter_config.json"
    adapter_config_path.write_text(
        json.dumps(
            {
                "tokenizer_config": {"eos_token": "<|saved-eos|>"},
                "callback_arity": 3,
                "expected_callback_arity": 2,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    weights_path = adapter_dir / "adapters.safetensors"
    weights_path.write_bytes(b"adapter")

    fields = build_lora_canary_receipt_fields(
        source_model=_text_model(model_path=str(base_model_dir)),
        adapter_output_dir=adapter_dir,
        adapter_config_path=adapter_config_path,
        weights_path=weights_path,
        training_metrics=TrainingMetrics(
            job_duration_ms=1.0,
            tokens_seen=8,
            examples_seen=1,
            loss_final=0.5,
            loss_best=0.5,
            learning_rate_final=1e-5,
        ),
    )

    assert fields["source_eos_token"] == ""
    assert fields["saved_eos_token"] == "<|saved-eos|>"
    assert fields["tokenizer_config_path"] == str(base_model_dir / "tokenizer_config.json")
    assert fields["base_config_present"] is True
    assert fields["processor_resume_mode"] == "tokenizer_only"
    assert fields["aux_modules_restored"] is False
    assert fields["merge_export_canary_result"] == "fail:missing_source_eos_token,missing_auxiliary_modules"
    assert fields["callback_api_drift_result"] == "fail:callback_arity_mismatch"


def test_normalize_training_config_rejects_qlora_for_non_quantized_profile() -> None:
    with pytest.raises(ModelOperationError) as exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(
                model_path="models/plain-gemma-bf16",
                quant_profile_id="bf16",
                family_id="gemma",
            ),
            ext={"training_mode": "qlora"},
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )

    assert exc.value.code == "unsupported_quantized_base"
    assert "requires a quantized base model" in exc.value.message


def test_multimodal_lora_finite_mask_handles_fully_padded_vision_rows() -> None:
    scores = [
        [[0.2, 0.1, -0.4], [1.0, -1.0, 0.0]],
        [[0.0, 0.0, 0.0], [0.5, 0.25, -0.5]],
    ]
    visible_mask = [
        [[True, True, False], [False, False, False]],
        [[True, False, False], [False, True, False]],
    ]

    probabilities, mask = finite_masked_softmax(scores, visible_mask, dtype="float16")

    assert mask.nan_guard_triggered is True
    assert mask.all_masked_row_count == 1
    assert mask.finite_floor == -1.0e4
    assert all(value != float("-inf") for batch in mask.additive_mask for row in batch for value in row)
    assert probabilities[0][1] == [0.0, 0.0, 0.0]
    for batch in probabilities:
        for row in batch:
            assert all(value == value for value in row)
            assert all(value not in {float("inf"), float("-inf")} for value in row)


def test_multimodal_lora_finite_mask_handles_empty_visible_rows() -> None:
    probabilities, mask = finite_masked_softmax([[1.0, 2.0]], [[]], dtype="float32")

    assert mask.additive_mask == [[]]
    assert probabilities == [[]]


def test_multimodal_lora_training_receipt_records_triggered_nan_guard(tmp_path: Path) -> None:
    class NanGuardRunner(DeterministicLoRARunner):
        def train_native(self, request: TrainingRequest) -> TrainingResult:
            result = super().train_native(request)
            return TrainingResult(
                weights_path=result.weights_path,
                adapter_config_path=result.adapter_config_path,
                execution_backend=result.execution_backend,
                metrics=TrainingMetrics(
                    **{
                        **result.metrics.__dict__,
                        "multimodal_lora_nan_guard_triggered": True,
                    }
                ),
            )

    component_model_dir = tmp_path / "gemma4-vlm-mixed"
    component_model_dir.mkdir()
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-mixed-modality",
        manifest_payload={
            "schema_version": "melix.training_dataset_package.v1",
            "dataset_id": "mixed-modality-padded-images",
            "format": "chat_messages",
            "sample_count": 2,
            "version": "1",
            "modalities": ["text", "image"],
            "image_shapes": [[256, 384], [384, 256]],
        },
        sample_lines=[
            json.dumps(
                {
                    "messages": [
                        {"role": "user", "content": "Describe the non-square image."},
                        {"role": "assistant", "content": "The image is non-square."},
                    ],
                    "media_refs": [{"id": "image-a", "uri": "images/a.png", "width": 256, "height": 384}],
                }
            ),
            json.dumps(
                {
                    "messages": [
                        {"role": "user", "content": "Describe the padded image."},
                        {"role": "assistant", "content": "The image includes padded regions."},
                    ],
                    "media_refs": [{"id": "image-b", "uri": "images/b.png", "width": 384, "height": 256}],
                }
            ),
        ],
    )

    result = LoRATrainingPipeline(runner=NanGuardRunner()).run(
        job_id="train-gemma4-vlm-nan-guard",
        request_ext={
            "operation": "train_lora",
            "adapter_name": "gemma4-padded-image-adapter",
            "dataset_uri": str(dataset_dir),
        },
        source_model=_gemma4_vlm_model(model_path=str(component_model_dir)),
        output_dir=tmp_path / "output-nan-guard",
        jobs_root=tmp_path / "jobs-nan-guard",
    )

    assert result.manifest["dataset_id"] == "mixed-modality-padded-images"
    assert result.manifest["multimodal_lora_nan_guard_triggered"] is True
    assert result.manifest["training.multimodal_lora_nan_guard_triggered"] is True
    assert result.manifest["unexpected_frozen_param_count"] == 0
    assert result.manifest["adapter_checkpoint_bytes"] > 0


def test_adapter_freeze_audit_rejects_serialized_vision_tower_weights(tmp_path: Path) -> None:
    weights_path = tmp_path / "adapters.safetensors"
    _write_safetensors_header(
        weights_path,
        {
            "model.layers.0.self_attn.q_proj.lora_a.weight": {
                "dtype": "F16",
                "shape": [2, 4],
                "data_offsets": [0, 16],
            },
            "vision_tower.encoder.layers.0.weight": {
                "dtype": "F16",
                "shape": [8, 8],
                "data_offsets": [16, 144],
            },
        },
    )

    audit = audit_adapter_checkpoint(
        weights_path=weights_path,
        allowed_target_modules=["model.layers.0.self_attn.q_proj"],
        source_model_kind="vlm",
        source_model_ext={},
    )

    assert audit.adapter_checkpoint_bytes == weights_path.stat().st_size
    assert audit.unexpected_frozen_param_count == 64
    assert audit.unexpected_serialized_param_count == 64
    assert audit.serialized_param_count_by_component["vision_encoder"] == 64
    assert audit.unexpected_serialized_parameters == ("vision_tower.encoder.layers.0.weight",)

    class LeakyRunner(DeterministicLoRARunner):
        def train_native(self, request):  # noqa: ANN001
            result = super().train_native(request)
            _write_safetensors_header(
                result.weights_path,
                {
                    "model.layers.1.self_attn.q_proj.lora_a.weight": {
                        "dtype": "F16",
                        "shape": [2, 4],
                        "data_offsets": [0, 16],
                    },
                    "vision_tower.encoder.layers.0.weight": {
                        "dtype": "F16",
                        "shape": [8, 8],
                        "data_offsets": [16, 144],
                    },
                },
            )
            return result

    component_model_dir = tmp_path / "gemma4-vlm"
    component_model_dir.mkdir()
    dataset_dir = _write_dataset_package(tmp_path / "dataset-leaky")

    with pytest.raises(ModelOperationError) as exc:
        LoRATrainingPipeline(runner=LeakyRunner()).run(
            job_id="train-gemma4-vlm-leaky",
            request_ext={
                "operation": "train_lora",
                "adapter_name": "gemma4-leaky-adapter",
                "dataset_uri": str(dataset_dir),
                "target_modules": "q_proj",
                "num_layers": "1",
            },
            source_model=_gemma4_vlm_model(model_path=str(component_model_dir)),
            output_dir=tmp_path / "output-leaky",
            jobs_root=tmp_path / "jobs-leaky",
        )

    assert exc.value.code == "adapter_freeze_audit_failed"
    assert exc.value.details["unexpected_serialized_param_count"] == "64"
    assert "vision_tower.encoder.layers.0.weight" in exc.value.details["unexpected_serialized_parameters"]


def test_adapter_freeze_audit_accepts_language_model_lora_suffix_for_last_layer(
    tmp_path: Path,
) -> None:
    weights_path = tmp_path / "gemma4-last-layer-adapter.safetensors"
    _write_safetensors_header(
        weights_path,
        {
            "language_model.model.layers.41.self_attn.q_proj.lora_a": {
                "dtype": "F32",
                "shape": [2560, 4],
                "data_offsets": [0, 40960],
            },
            "language_model.model.layers.41.self_attn.q_proj.lora_b": {
                "dtype": "F32",
                "shape": [4, 4096],
                "data_offsets": [40960, 106496],
            },
        },
    )

    audit = audit_adapter_checkpoint(
        weights_path=weights_path,
        allowed_target_modules=["model.layers.0.self_attn.q_proj"],
        source_model_kind="vlm",
        source_model_ext={},
        live_audit={
            "unexpected_trainable_param_count": 0,
            "unexpected_trainable_parameters": [],
            "unexpected_trainable_param_counts": {},
            "trainable_param_count_by_component": {"text_backbone": 26624},
        },
    )

    assert audit.unexpected_frozen_param_count == 0
    assert audit.unexpected_serialized_param_count == 0
    assert audit.unexpected_trainable_param_count == 0
    assert audit.serialized_param_count_by_component["text_backbone"] == 26624


def test_adapter_freeze_audit_accepts_leaf_target_module_names(tmp_path: Path) -> None:
    weights_path = tmp_path / "leaf-target-adapter.safetensors"
    _write_safetensors_header(
        weights_path,
        {
            "language_model.model.layers.41.self_attn.q_proj.lora_a.weight": {
                "dtype": "F16",
                "shape": [2, 4],
                "data_offsets": [0, 16],
            },
        },
    )

    audit = audit_adapter_checkpoint(
        weights_path=weights_path,
        allowed_target_modules=["q_proj"],
        source_model_kind="vlm",
        source_model_ext={},
    )

    assert audit.unexpected_serialized_param_count == 0
    assert audit.unexpected_frozen_param_count == 0
    assert audit.serialized_param_count_by_component["text_backbone"] == 8


def test_adapter_parameter_fragment_matching_handles_empty_and_generic_fragments() -> None:
    assert _adapter_parameter_matches_fragment(
        "model.layers.0.self_attn.q_proj.lora_a.weight",
        "",
    ) is False
    assert _adapter_parameter_matches_fragment(
        "model.layers.0.self_attn.q_proj.lora_a.weight",
        "model.layers.self_attn.weight",
    ) is False


def test_adapter_freeze_audit_rejects_wrong_target_fragment_for_adapter_weight(
    tmp_path: Path,
) -> None:
    weights_path = tmp_path / "wrong-target-fragment.safetensors"
    _write_safetensors_header(
        weights_path,
        {
            "model.layers.0.self_attn.q_proj.lora_a.weight": {
                "dtype": "F16",
                "shape": [2, 4],
                "data_offsets": [0, 16],
            },
        },
    )

    audit = audit_adapter_checkpoint(
        weights_path=weights_path,
        allowed_target_modules=["k_proj"],
        source_model_kind="vlm",
        source_model_ext={},
    )

    assert audit.unexpected_serialized_param_count == 8
    assert audit.unexpected_serialized_parameters == (
        "model.layers.0.self_attn.q_proj.lora_a.weight",
    )


def test_adapter_freeze_audit_deduplicates_live_and_serialized_leaks(tmp_path: Path) -> None:
    weights_path = tmp_path / "duplicate-leak.safetensors"
    leaked_name = "vision_tower.encoder.layers.0.weight"
    _write_safetensors_header(
        weights_path,
        {
            "model.layers.0.self_attn.q_proj.lora_a.weight": {
                "dtype": "F16",
                "shape": [2, 4],
                "data_offsets": [0, 16],
            },
            leaked_name: {
                "dtype": "F16",
                "shape": [8, 8],
                "data_offsets": [16, 144],
            },
        },
    )

    audit = audit_adapter_checkpoint(
        weights_path=weights_path,
        allowed_target_modules=["model.layers.0.self_attn.q_proj"],
        source_model_kind="vlm",
        source_model_ext={},
        live_audit={
            "unexpected_trainable_param_count": 64,
            "unexpected_trainable_parameters": [leaked_name],
            "unexpected_trainable_param_counts": {leaked_name: 64},
            "trainable_param_count_by_component": {"vision_encoder": 64},
        },
    )

    assert audit.unexpected_serialized_param_count == 64
    assert audit.unexpected_trainable_param_count == 64
    assert audit.unexpected_frozen_param_count == 64
    assert audit.unexpected_serialized_param_counts == {leaked_name: 64}
    assert audit.unexpected_trainable_param_counts == {leaked_name: 64}


def test_adapter_freeze_audit_does_not_block_on_live_only_trainable_noise(tmp_path: Path) -> None:
    weights_path = tmp_path / "clean-adapter-with-live-noise.safetensors"
    _write_safetensors_header(
        weights_path,
        {
            "language_model.model.layers.58.self_attn.q_proj.lora_a": {
                "dtype": "F16",
                "shape": [2, 4],
                "data_offsets": [0, 16],
            },
            "language_model.model.layers.58.self_attn.q_proj.lora_b": {
                "dtype": "F16",
                "shape": [4, 2],
                "data_offsets": [16, 32],
            },
        },
    )

    audit = audit_adapter_checkpoint(
        weights_path=weights_path,
        allowed_target_modules=["model.layers.58.self_attn.q_proj"],
        source_model_kind="text",
        source_model_ext={},
        live_audit={
            "unexpected_trainable_param_count": 8,
            "unexpected_trainable_parameters": ["adapter_noise.internal_state"],
            "unexpected_trainable_param_counts": {"adapter_noise.internal_state": 8},
            "trainable_param_count_by_component": {"adapter_noise": 8},
        },
    )

    assert audit.unexpected_serialized_param_count == 0
    assert audit.unexpected_trainable_param_count == 8
    assert audit.unexpected_frozen_param_count == 0
    assert audit.unexpected_trainable_param_counts == {"adapter_noise.internal_state": 8}


def test_adapter_freeze_audit_rejects_full_base_weights_under_allowed_target(tmp_path: Path) -> None:
    weights_path = tmp_path / "base-weight-leak.safetensors"
    _write_safetensors_header(
        weights_path,
        {
            "model.layers.0.self_attn.q_proj.lora_a.weight": {
                "dtype": "F16",
                "shape": [2, 4],
                "data_offsets": [0, 16],
            },
            "model.layers.0.self_attn.q_proj.weight": {
                "dtype": "F16",
                "shape": [4, 4],
                "data_offsets": [16, 48],
            },
        },
    )

    audit = audit_adapter_checkpoint(
        weights_path=weights_path,
        allowed_target_modules=["model.layers.0.self_attn.q_proj"],
        source_model_kind="vlm",
        source_model_ext={},
    )

    assert audit.unexpected_serialized_param_count == 16
    assert audit.unexpected_serialized_parameters == ("model.layers.0.self_attn.q_proj.weight",)
    assert audit.serialized_param_count_by_component["text_backbone"] == 24


def test_adapter_freeze_audit_ignores_invalid_large_safetensors_header(tmp_path: Path) -> None:
    weights_path = tmp_path / "oversized-header.safetensors"
    weights_path.write_bytes((9 * 1024 * 1024).to_bytes(8, "little"))

    audit = audit_adapter_checkpoint(
        weights_path=weights_path,
        allowed_target_modules=["model.layers.0.self_attn.q_proj"],
        source_model_kind="vlm",
        source_model_ext={},
    )

    assert audit.adapter_checkpoint_bytes == 8
    assert audit.unexpected_frozen_param_count == 0
    assert audit.unexpected_serialized_param_count == 0
    assert audit.serialized_param_count_by_component == {}


def _write_safetensors_header(path: Path, tensors: dict[str, dict[str, object]]) -> None:
    header = json.dumps(tensors, separators=(",", ":")).encode("utf-8")
    tensor_bytes = max(
        (
            int(metadata["data_offsets"][1])
            for metadata in tensors.values()
            if isinstance(metadata.get("data_offsets"), list)
        ),
        default=0,
    )
    path.write_bytes(len(header).to_bytes(8, "little") + header + (b"\0" * tensor_bytes))


def test_checkpoint_summary_uses_scandir_stack_without_os_walk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    adapter_dir = tmp_path / "adapter"
    checkpoint_one = adapter_dir / "checkpoint-1"
    checkpoint_two = adapter_dir / "checkpoint-2"
    checkpoint_one.mkdir(parents=True)
    checkpoint_two.mkdir(parents=True)
    (adapter_dir / "adapters.safetensors").write_text("root", encoding="utf-8")
    (checkpoint_one / "adapters.safetensors").write_text("one", encoding="utf-8")
    latest_path = checkpoint_two / "adapters.safetensors"
    latest_path.write_text("two", encoding="utf-8")

    def fail_os_walk(path: str):
        raise AssertionError("expected explicit os.scandir stack, not os.walk")

    monkeypatch.setattr(os, "walk", fail_os_walk)

    assert mlx_lm_runner_module._checkpoint_summary(adapter_dir) == (2, str(latest_path))


def test_checkpoint_summary_handles_empty_or_missing_directories(tmp_path: Path) -> None:
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "README.txt").write_text("no checkpoints", encoding="utf-8")

    assert mlx_lm_runner_module._checkpoint_summary(adapter_dir) == (0, "")
    assert mlx_lm_runner_module._checkpoint_summary(tmp_path / "missing") == (0, "")


def test_mlx_lora_namespace_uses_dora_fine_tune_type(tmp_path: Path) -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={"training_mode": "dora"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-dora",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=tmp_path / "normalized",
        config=config,
        dataset_format="chat_messages",
    )

    assert mlx_lm_runner_module._mlx_lora_namespace(request).fine_tune_type == "dora"


def test_mlx_lora_namespace_exposes_adapter_capability_receipt(tmp_path: Path) -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(
            model_path="mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            quant_profile_id="q4",
        ),
        ext={"training_mode": "qlora"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-qlora",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=tmp_path / "normalized",
        config=config,
        dataset_format="chat_messages",
    )

    namespace = mlx_lm_runner_module._mlx_lora_namespace(request)

    assert namespace.fine_tune_type == "lora"
    assert namespace.adapter_family == "qlora"
    assert namespace.adapter_capabilities["quantized_base_supported"] is True
    assert namespace.adapter_loader_kwargs == {}


def test_mlx_lm_runner_routes_alignment_rl_to_scored_trace_backend(tmp_path: Path) -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={"training_mode": "grpo", "grpo_candidate_count": "2", "kl_penalty": "0.05"},
        dataset_format="prompt_candidate",
        response_only_supported=False,
        sample_count=1,
    )
    normalized_dataset_dir = tmp_path / "normalized"
    normalized_dataset_dir.mkdir()
    (normalized_dataset_dir / "train.jsonl").write_text(
        "\n"
        + json.dumps(
            {
                "prompt": "Draft two summaries.",
                "candidates": [
                    {"text": "Short summary.", "score": 0.7},
                    {"text": "Verbose summary.", "score": 0.4},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-grpo",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=normalized_dataset_dir,
        config=config,
        dataset_format="prompt_candidate",
    )

    result = mlx_lm_runner_module.MLXLMRunner().train(request)

    assert result.execution_backend == "scored_trace"
    assert result.weights_path.read_bytes()
    assert json.loads(result.adapter_config_path.read_text(encoding="utf-8"))["alignment_algorithm"] == "grpo"
    assert result.metrics.examples_seen == 1
    assert result.metrics.policy_update_count == 1
    assert result.metrics.selected_candidate_count == 1
    assert result.metrics.reward_mean == pytest.approx(0.55)
    assert result.metrics.reward_p50 == pytest.approx(0.55)
    assert result.metrics.candidate_group_reward_margin_mean == pytest.approx(0.3)
    assert result.metrics.candidate_group_reward_variance_mean == pytest.approx(0.0225)
    assert result.metrics.policy_update_trace_path.endswith("policy_updates.jsonl")


def test_mlx_lm_runner_alignment_rl_reuses_agentic_tool_runtime(tmp_path: Path) -> None:
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
                "prompt": "Use tools before choosing.",
                "tool_calls": [
                    {
                        "id": "visit-1",
                        "name": "visit",
                        "arguments": {"url": "fixture://doc"},
                    }
                ],
                "tool_fixture_context": {
                    "pages": {"fixture://doc": {"title": "Doc", "text": "Helpful source."}},
                },
                "candidates": [
                    {"text": "Tool-backed answer.", "score": 0.9},
                    {"text": "Guess.", "score": 0.1},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-grpo-tools",
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

    assert trace_rows[0]["agentic_tool_registry"]["toolset_version"] == "melix.agentic_tools.builtin.v1"
    assert trace_rows[0]["agentic_tool_calls"][0]["name"] == "visit"
    assert trace_rows[0]["agentic_tool_observations"][0]["payload"]["text"] == "Helpful source."
    assert trace_rows[0]["agentic_tool_metrics"]["agentic_tool.call_count"] == 1.0
    assert trace_rows[0]["turns"][0]["tool_call"]["id"] == "visit-1"


def test_alignment_rl_tool_helpers_cover_empty_and_rlhf_paths() -> None:
    from worker.model_ops.rl_alignment_training import (
        _agentic_tool_run_for_sample,
        _attach_agentic_tool_run,
        _rlhf_policy_updates,
    )

    row: dict[str, object] = {}
    _attach_agentic_tool_run(row, None)
    assert row == {}
    assert _agentic_tool_run_for_sample({"tool_calls": "not-a-list"}) is None

    result = _rlhf_policy_updates(
        [
            {
                "prompt": "Read page.",
                "response": "Done.",
                "reward_score": 0.8,
                "tool_calls": [
                    {"id": "visit-1", "name": "visit", "arguments": {"url": "fixture://doc"}}
                ],
                "tool_context": {
                    "pages": {"fixture://doc": {"title": "Doc", "text": "RLHF page."}},
                },
            }
        ]
    )

    assert result.trace_rows[0]["agentic_tool_calls"][0]["name"] == "visit"
    assert result.trace_rows[0]["agentic_tool_observations"][0]["payload"]["text"] == "RLHF page."


def test_mlx_lm_runner_alignment_rl_preserves_source_adapter_artifacts(tmp_path: Path) -> None:
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
                "prompt": "Draft two summaries.",
                "candidates": [
                    {"text": "Short summary.", "score": 0.7},
                    {"text": "Verbose summary.", "score": 0.4},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    source_adapter_dir = tmp_path / "source-adapter"
    source_adapter_dir.mkdir()
    source_weights = source_adapter_dir / "adapters.safetensors"
    source_weights.write_bytes(b"real-mlx-lora-weights")
    (source_adapter_dir / "adapter_config.json").write_text(
        json.dumps(
            {
                "adapter_path": str(source_adapter_dir),
                "fine_tune_type": "lora",
                "num_layers": 2,
                "lora_parameters": {"keys": ["self_attn.q_proj"], "rank": 8},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-grpo-source-adapter",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=normalized_dataset_dir,
        config=config,
        dataset_format="prompt_candidate",
        resume_source_path=source_weights,
    )

    result = mlx_lm_runner_module.MLXLMRunner().train(request)
    adapter_config = json.loads(result.adapter_config_path.read_text(encoding="utf-8"))

    assert result.weights_path.read_bytes() == b"real-mlx-lora-weights"
    assert Path(result.metrics.latest_checkpoint_path).read_bytes() == b"real-mlx-lora-weights"
    assert adapter_config["adapter_path"] == str(tmp_path / "adapter-output")
    assert adapter_config["num_layers"] == 2
    assert adapter_config["lora_parameters"]["keys"] == ["self_attn.q_proj"]
    assert adapter_config["alignment_algorithm"] == "grpo"
    assert adapter_config["alignment_source_adapter_weights_path"] == str(source_weights)
    assert result.metrics.resume_source_path == str(source_weights)


def test_alignment_rl_rejects_missing_source_adapter_weights(tmp_path: Path) -> None:
    from worker.model_ops.rl_alignment_training import _alignment_adapter_weights_bytes

    missing_weights = tmp_path / "missing-adapters.safetensors"
    with pytest.raises(ModelOperationError) as exc:
        _alignment_adapter_weights_bytes(
            source_weights_path=missing_weights,
            job_id="train-grpo-missing-source",
            base_model_id="melix-dev-text",
            alignment_algorithm="grpo",
            trace_rows=[],
        )

    assert exc.value.code == "invalid_resume_source"
    assert exc.value.details["source_weights_path"] == str(missing_weights)


def test_mlx_lm_runner_generates_grpo_candidates_with_policy_runtime(tmp_path: Path) -> None:
    class ScriptedPolicyBackend:
        runtime_name = "scripted-policy-runtime"

        def __init__(self) -> None:
            self.loaded_model_path = ""
            self.prompts: list[str] = []

        def load_model(self, model_spec):
            self.loaded_model_path = model_spec.model_path
            return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

        def estimate_resident_bytes(self, model_spec) -> int:
            return 1

        def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event, execution_ext=None):
            del loaded_model, sampling, execution_ext
            self.prompts.append(prompt)
            if cancel_event.is_set():
                return
            if "candidate 1" in prompt:
                yield RuntimeTokenEvent(text="preferred concise answer")
            else:
                yield RuntimeTokenEvent(text="weak answer")

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
                "prompt": "Draft two summaries.",
                "candidates": [
                    {"text": "preferred concise answer", "score": 1.0},
                    {"text": "weak answer", "score": 0.2},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    backend = ScriptedPolicyBackend()
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-grpo-runtime",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=normalized_dataset_dir,
        config=config,
        dataset_format="prompt_candidate",
    )

    result = mlx_lm_runner_module.MLXLMRunner(
        policy_runtime=MLXTextRuntime(backend=backend)
    ).train(request)

    trace_rows = [
        json.loads(line)
        for line in Path(result.metrics.policy_update_trace_path).read_text(encoding="utf-8").splitlines()
    ]
    adapter_config = json.loads(result.adapter_config_path.read_text(encoding="utf-8"))

    assert result.execution_backend == "runtime_generated_scored_trace"
    assert backend.loaded_model_path == str(tmp_path / "base-model")
    assert len(backend.prompts) == 2
    assert result.metrics.candidate_generation_mode == "runtime_generate"
    assert result.metrics.candidate_generation_backend == "scripted-policy-runtime"
    assert result.metrics.candidate_scoring_mode == "seed_overlap_proxy"
    assert result.metrics.generated_candidate_count == 2
    assert result.metrics.reward_mean == pytest.approx(2 / 3)
    assert trace_rows[0]["generated_candidates"][0]["score"] == pytest.approx(1.0)
    assert trace_rows[0]["generated_candidates"][1]["score"] == pytest.approx(1 / 3)
    assert trace_rows[0]["selected_candidate_text"] == "preferred concise answer"
    assert adapter_config["candidate_generation_mode"] == "runtime_generate"
    assert adapter_config["candidate_generation_backend"] == "scripted-policy-runtime"


def test_mlx_lm_runner_scores_generated_grpo_candidates_with_reward_model(
    tmp_path: Path,
) -> None:
    class ScriptedPolicyBackend:
        runtime_name = "scripted-policy-runtime"

        def load_model(self, model_spec):
            return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

        def estimate_resident_bytes(self, model_spec) -> int:
            return 1

        def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event, execution_ext=None):
            del loaded_model, sampling, execution_ext
            if cancel_event.is_set():
                return
            if "candidate 1" in prompt:
                yield RuntimeTokenEvent(text="clear helpful answer")
            else:
                yield RuntimeTokenEvent(text="terse answer")

    class ScriptedRewardBackend:
        runtime_name = "scripted-reward-runtime"

        def __init__(self) -> None:
            self.loaded_model_path = ""
            self.scored_responses: list[str] = []

        def load_model(self, model_spec):
            self.loaded_model_path = model_spec.model_path
            return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

        def estimate_resident_bytes(self, model_spec) -> int:
            return 1

        def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event, execution_ext=None):
            del loaded_model, prompt, sampling, cancel_event, execution_ext
            return
            yield

        def score_response(self, loaded_model, prompt: str, response: str, execution_ext=None):
            del loaded_model, prompt, execution_ext
            self.scored_responses.append(response)
            return 0.9 if "clear helpful" in response else 0.2

    reward_model_dir = tmp_path / "reward-model"
    reward_model_dir.mkdir()
    reward_manifest_path = reward_model_dir / "manifest.json"
    reward_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.reward_model_adapter.v1",
                "reward_model_id": "helpfulness-reward",
                "model_path": str(reward_model_dir),
                "reward_head_type": "scalar",
                "score_scale": "0_to_1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={
            "training_mode": "grpo",
            "grpo_candidate_count": "2",
            "candidate_generation_mode": "runtime_generate",
            "candidate_scoring_mode": "reward_model",
            "reward_model_manifest_path": str(reward_manifest_path),
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
                "prompt": "Draft two answers.",
                "candidates": [
                    {"text": "seed answer one"},
                    {"text": "seed answer two"},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    reward_backend = ScriptedRewardBackend()
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-grpo-runtime-reward",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=normalized_dataset_dir,
        config=config,
        dataset_format="prompt_candidate",
    )

    result = mlx_lm_runner_module.MLXLMRunner(
        policy_runtime=MLXTextRuntime(backend=ScriptedPolicyBackend()),
        reward_runtime=MLXTextRuntime(backend=reward_backend),
    ).train(request)

    trace_rows = [
        json.loads(line)
        for line in Path(result.metrics.policy_update_trace_path).read_text(encoding="utf-8").splitlines()
    ]
    adapter_config = json.loads(result.adapter_config_path.read_text(encoding="utf-8"))

    assert result.execution_backend == "runtime_generated_reward_model"
    assert reward_backend.loaded_model_path == str(reward_model_dir)
    assert reward_backend.scored_responses == ["clear helpful answer", "terse answer"]
    assert result.metrics.candidate_scoring_mode == "reward_model"
    assert result.metrics.reward_scoring_backend == "scripted-reward-runtime"
    assert result.metrics.reward_mean == pytest.approx(0.55)
    assert trace_rows[0]["reward_model_id"] == "helpfulness-reward"
    assert trace_rows[0]["reward_scoring_backend"] == "scripted-reward-runtime"
    assert trace_rows[0]["selected_candidate_text"] == "clear helpful answer"
    assert trace_rows[0]["generated_candidates"][0]["score"] == pytest.approx(0.9)
    assert adapter_config["reward_scoring_backend"] == "scripted-reward-runtime"


def test_mlx_lm_runner_scores_rlhf_responses_with_reward_model(tmp_path: Path) -> None:
    class ScriptedRewardBackend:
        runtime_name = "scripted-reward-runtime"

        def load_model(self, model_spec):
            return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

        def estimate_resident_bytes(self, model_spec) -> int:
            return 1

        def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event, execution_ext=None):
            del loaded_model, prompt, sampling, cancel_event, execution_ext
            return
            yield

        def score_response(self, loaded_model, prompt: str, response: str, execution_ext=None):
            del loaded_model, prompt, execution_ext
            return 0.8 if "useful" in response else 0.1

    reward_model_dir = tmp_path / "reward-model"
    reward_model_dir.mkdir()
    reward_manifest_path = reward_model_dir / "manifest.json"
    reward_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.reward_model_adapter.v1",
                "reward_model_id": "rlhf-reward",
                "model_path": str(reward_model_dir),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={
            "training_mode": "rlhf",
            "reward_model_manifest_path": str(reward_manifest_path),
            "candidate_scoring_mode": "reward_model",
        },
        dataset_format="reward_scored",
        response_only_supported=False,
        sample_count=1,
    )
    normalized_dataset_dir = tmp_path / "normalized"
    normalized_dataset_dir.mkdir()
    (normalized_dataset_dir / "train.jsonl").write_text(
        json.dumps(
            {
                "prompt": "Rate this answer.",
                "response": "A useful answer.",
                "reward_score": 0.2,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-rlhf-reward",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=normalized_dataset_dir,
        config=config,
        dataset_format="reward_scored",
    )

    result = mlx_lm_runner_module.MLXLMRunner(
        reward_runtime=MLXTextRuntime(backend=ScriptedRewardBackend()),
    ).train(request)

    trace_rows = [
        json.loads(line)
        for line in Path(result.metrics.policy_update_trace_path).read_text(encoding="utf-8").splitlines()
    ]

    assert result.execution_backend == "reward_model_scored_trace"
    assert result.metrics.candidate_scoring_mode == "reward_model"
    assert result.metrics.reward_scoring_backend == "scripted-reward-runtime"
    assert result.metrics.reward_mean == pytest.approx(0.8)
    assert trace_rows[0]["selected_reward"] == pytest.approx(0.8)
    assert trace_rows[0]["dataset_reward_score"] == pytest.approx(0.2)
    assert trace_rows[0]["reward_model_id"] == "rlhf-reward"


def test_alignment_rl_reward_model_scoring_helpers_cover_trace_and_error_paths(
    tmp_path: Path,
) -> None:
    from worker.model_ops.rl_alignment_training import (
        RewardModelScorer,
        _grpo_policy_updates,
        _load_reward_model_manifest,
        _missing_reward_scorer_error,
        _resolve_reward_model_scorer,
        _reward_model_spec_from_manifest,
        _rlhf_policy_updates,
    )

    class DirectRewardRuntime:
        runtime_name = "direct-reward-runtime"

        def __init__(self) -> None:
            self.responses: list[str] = []

        def score_response(self, loaded_model, prompt: str, response: str, execution_ext=None):
            del loaded_model, prompt, execution_ext
            self.responses.append(response)
            return 0.6 if "best" in response else 0.1

    reward_runtime = DirectRewardRuntime()
    reward_scorer = RewardModelScorer(
        runtime=reward_runtime,
        loaded_model={},
        runtime_name=reward_runtime.runtime_name,
        manifest_path=str(tmp_path / "reward-model" / "manifest.json"),
        reward_model_id="direct-reward",
    )

    grpo_result = _grpo_policy_updates(
        [
            {
                "prompt": "Pick a candidate.",
                "candidates": [{"text": "best answer"}, {"text": "weak answer"}],
            }
        ],
        candidate_count=2,
        candidate_scoring_mode="reward_model",
        reward_scorer=reward_scorer,
    )

    assert grpo_result.execution_backend == "reward_model_scored_trace"
    assert grpo_result.reward_scoring_backend == "direct-reward-runtime"
    assert grpo_result.reward_values == [0.6, 0.1]
    assert grpo_result.trace_rows[0]["reward_model_id"] == "direct-reward"
    assert reward_runtime.responses == ["best answer", "weak answer"]

    with pytest.raises(ModelOperationError) as grpo_missing:
        _grpo_policy_updates(
            [{"prompt": "Pick.", "candidates": [{"text": "A"}, {"text": "B"}]}],
            candidate_count=2,
            candidate_scoring_mode="reward_model",
        )
    assert grpo_missing.value.details["missing_field"] == "reward_runtime"

    with pytest.raises(ModelOperationError) as rlhf_missing:
        _rlhf_policy_updates(
            [{"prompt": "Rate.", "response": "Useful.", "reward_score": 0.3}],
            candidate_scoring_mode="reward_model",
        )
    assert rlhf_missing.value.details["missing_field"] == "reward_runtime"

    assert _missing_reward_scorer_error().code == "unsupported_alignment_trainer"
    assert _resolve_reward_model_scorer(
        types.SimpleNamespace(candidate_scoring_mode="dataset_score"),
        reward_runtime=None,
    ) is None

    manifest_path = tmp_path / "reward-model" / "manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.reward_model_adapter.v1",
                "reward_model_id": "fallback-reward",
                "reward_head_type": "scalar",
                "score_prompt_template": "Prompt={prompt}\nResponse={response}\nScore:",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_payload = _load_reward_model_manifest(manifest_path)
    reward_model_spec = _reward_model_spec_from_manifest(manifest_path, manifest_payload)
    assert reward_model_spec.model_id == "fallback-reward"
    assert reward_model_spec.model_path == str(manifest_path.parent)
    assert reward_model_spec.ext["melix.reward_model.reward_head_type"] == "scalar"
    assert reward_model_spec.ext["melix.reward_model.score_prompt_template"].startswith("Prompt=")

    with pytest.raises(ModelOperationError) as missing_manifest:
        _load_reward_model_manifest(tmp_path / "missing" / "manifest.json")
    assert missing_manifest.value.code == "invalid_alignment_config"

    malformed_manifest = tmp_path / "malformed-reward.json"
    malformed_manifest.write_text("{bad-json\n", encoding="utf-8")
    with pytest.raises(ModelOperationError, match="readable JSON"):
        _load_reward_model_manifest(malformed_manifest)

    schema_missing_manifest = tmp_path / "schema-missing-reward.json"
    schema_missing_manifest.write_text(json.dumps({"reward_model_id": "bad"}) + "\n", encoding="utf-8")
    with pytest.raises(ModelOperationError, match="schema_version"):
        _load_reward_model_manifest(schema_missing_manifest)


def test_alignment_rl_reward_model_runtime_errors_are_reported(tmp_path: Path) -> None:
    from worker.model_ops.rl_alignment_training import (
        RewardModelScorer,
        _resolve_reward_model_scorer,
    )

    class MissingScoreRuntime:
        runtime_name = "missing-score-runtime"

    missing_score_scorer = RewardModelScorer(
        runtime=MissingScoreRuntime(),
        loaded_model={},
        runtime_name="missing-score-runtime",
        manifest_path=str(tmp_path / "reward" / "manifest.json"),
        reward_model_id="reward",
    )
    with pytest.raises(ModelOperationError) as missing_score:
        missing_score_scorer.score_response(
            prompt="Prompt.",
            response="Response.",
            alignment_algorithm="rlhf",
            sample_index=0,
        )
    assert missing_score.value.code == "unsupported_alignment_trainer"

    class ExplodingScoreRuntime:
        runtime_name = "exploding-score-runtime"

        def score_response(self, loaded_model, prompt: str, response: str, execution_ext=None):
            del loaded_model, prompt, response, execution_ext
            raise RuntimeError("score failed")

    exploding_scorer = RewardModelScorer(
        runtime=ExplodingScoreRuntime(),
        loaded_model={},
        runtime_name="exploding-score-runtime",
        manifest_path=str(tmp_path / "reward" / "manifest.json"),
        reward_model_id="reward",
    )
    with pytest.raises(ModelOperationError) as scoring_failed:
        exploding_scorer.score_response(
            prompt="Prompt.",
            response="Response.",
            alignment_algorithm="grpo",
            sample_index=1,
            candidate_index=2,
        )
    assert scoring_failed.value.code == "reward_model_scoring_failed"

    reward_manifest_path = tmp_path / "reward-manifest.json"
    reward_manifest_path.write_text(
        json.dumps({"schema_version": "melix.reward_model_adapter.v1"}) + "\n",
        encoding="utf-8",
    )

    class FailingLoadRuntime:
        runtime_name = "failing-load-runtime"

        def load_model(self, model_spec):
            del model_spec
            raise RuntimeError("load failed")

    with pytest.raises(ModelOperationError) as load_failed:
        _resolve_reward_model_scorer(
            types.SimpleNamespace(
                candidate_scoring_mode="reward_model",
                reward_model_manifest_path=str(reward_manifest_path),
            ),
            reward_runtime=FailingLoadRuntime(),
        )
    assert load_failed.value.code == "reward_model_load_failed"


def test_text_runtime_score_response_delegates_backend_and_executor() -> None:
    class PlainScoringBackend:
        runtime_name = "plain-scoring-runtime"

        def load_model(self, model_spec):
            return {"model_id": model_spec.model_id}

        def estimate_resident_bytes(self, model_spec) -> int:
            return 1

        def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event, execution_ext=None):
            del loaded_model, prompt, sampling, cancel_event, execution_ext
            return
            yield

        def score_response(self, loaded_model, prompt: str, response: str):
            del loaded_model, prompt
            return 0.7 if response else 0.0

    class Executor:
        def __init__(self) -> None:
            self.calls = 0

        def run(self, callback):
            self.calls += 1
            return callback()

    runtime = MLXTextRuntime(backend=PlainScoringBackend())
    assert runtime.score_response({}, "Prompt.", "Response.") == pytest.approx(0.7)

    executor = Executor()
    executor_runtime = MLXTextRuntime(backend=PlainScoringBackend(), executor=executor)
    assert executor_runtime.score_response({}, "Prompt.", "Response.") == pytest.approx(0.7)
    assert executor.calls == 1

    class MissingScoreBackend:
        def estimate_resident_bytes(self, model_spec) -> int:
            return 1

    with pytest.raises(RuntimeUnavailableError):
        MLXTextRuntime(backend=MissingScoreBackend()).score_response({}, "Prompt.", "Response.")


def test_lora_training_pipeline_wires_reward_runtime_into_default_runner(tmp_path: Path) -> None:
    class RewardBackend:
        runtime_name = "pipeline-reward-runtime"

        def __init__(self) -> None:
            self.loaded_model_path = ""
            self.responses: list[str] = []

        def load_model(self, model_spec):
            self.loaded_model_path = model_spec.model_path
            return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

        def score_response(self, loaded_model, prompt: str, response: str, execution_ext=None):
            del loaded_model, prompt, execution_ext
            self.responses.append(response)
            return 0.82

    reward_model_dir = tmp_path / "reward-model"
    reward_model_dir.mkdir()
    reward_manifest_path = reward_model_dir / "manifest.json"
    reward_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.reward_model_adapter.v1",
                "reward_model_id": "pipeline-reward",
                "model_path": str(reward_model_dir),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    dataset_dir = _write_dataset_package(
        tmp_path / "reward-scored-dataset",
        manifest_payload={
            "schema_version": "melix.training_dataset_package.v1",
            "dataset_id": "reward-scored",
            "format": "reward_scored",
            "sample_count": 1,
            "version": "1",
        },
        sample_lines=[
            json.dumps(
                {
                    "prompt": "Assess the response.",
                    "response": "Helpful response.",
                    "reward_score": 0.3,
                }
            )
        ],
    )
    reward_backend = RewardBackend()
    pipeline = LoRATrainingPipeline(
        policy_runtime=MLXTextRuntime(backend=RewardBackend()),
        reward_runtime=MLXTextRuntime(backend=reward_backend),
    )

    result = pipeline.run(
        job_id="reward-runtime-pipeline",
        request_ext={
            "operation": "train_lora",
            "training_mode": "rlhf",
            "adapter_name": "reward-runtime-adapter",
            "dataset_uri": str(dataset_dir),
            "reward_model_manifest_path": str(reward_manifest_path),
            "candidate_scoring_mode": "reward_model",
        },
        source_model=_text_model(model_path=str(tmp_path / "policy-model")),
        output_dir=tmp_path / "output",
        jobs_root=tmp_path / "jobs",
    )

    alignment_payload = json.loads(
        Path(result.manifest["alignment_run_manifest_path"]).read_text(encoding="utf-8")
    )
    assert reward_backend.loaded_model_path == str(reward_model_dir)
    assert reward_backend.responses == ["Helpful response."]
    assert alignment_payload["training_backend"] == "reward_model_scored_trace"
    assert alignment_payload["metrics"]["reward_scoring_backend"] == "pipeline-reward-runtime"
    assert alignment_payload["metrics"]["reward_mean"] == pytest.approx(0.82)


@pytest.mark.parametrize(
    ("training_mode", "dataset_format", "ext", "expected_message"),
    [
        (
            "grpo",
            "prompt_candidate",
            {
                "training_mode": "grpo",
                "grpo_candidate_count": "2",
                "candidate_generation_mode": "remote",
            },
            "Unsupported candidate_generation_mode",
        ),
        (
            "rlhf",
            "reward_scored",
            {
                "training_mode": "rlhf",
                "reward_model_manifest_path": "/tmp/reward/manifest.json",
                "candidate_generation_mode": "runtime_generate",
            },
            "only supported for GRPO",
        ),
        (
            "grpo",
            "prompt_candidate",
            {
                "training_mode": "grpo",
                "grpo_candidate_count": "2",
                "candidate_generation_mode": "runtime_generate",
                "candidate_scoring_mode": "dataset_score",
            },
            "candidate_scoring_mode=dataset_score is not supported",
        ),
        (
            "grpo",
            "prompt_candidate",
            {
                "training_mode": "grpo",
                "grpo_candidate_count": "2",
                "candidate_scoring_mode": "reward_model",
            },
            "requires reward_model_manifest_path",
        ),
        (
            "dpo",
            "preference_pair",
            {
                "training_mode": "dpo",
                "candidate_scoring_mode": "reward_model",
            },
            "candidate_scoring_mode=reward_model is not supported",
        ),
    ],
)
def test_alignment_config_rejects_invalid_candidate_generation_options(
    tmp_path: Path,
    training_mode: str,
    dataset_format: str,
    ext: dict[str, str],
    expected_message: str,
) -> None:
    del training_mode

    with pytest.raises(ModelOperationError) as exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(model_path=str(tmp_path / "base-model")),
            ext=ext,
            dataset_format=dataset_format,
            response_only_supported=False,
            sample_count=1,
        )

    assert expected_message in exc.value.message


def test_alignment_rl_runtime_generation_requires_policy_runtime(tmp_path: Path) -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={
            "training_mode": "grpo",
            "grpo_candidate_count": "2",
            "candidate_generation_mode": "runtime_generate",
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
                "prompt": "Draft two summaries.",
                "candidates": [
                    {"text": "Preferred.", "score": 1.0},
                    {"text": "Rejected.", "score": 0.0},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-grpo-runtime-missing",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=normalized_dataset_dir,
        config=config,
        dataset_format="prompt_candidate",
    )

    with pytest.raises(ModelOperationError) as exc:
        mlx_lm_runner_module.MLXLMRunner().train(request)

    assert exc.value.code == "unsupported_alignment_trainer"
    assert exc.value.details["candidate_generation_mode"] == "runtime_generate"


def test_alignment_rl_runtime_generation_rejects_empty_generation_and_unscored_seed(
    tmp_path: Path,
) -> None:
    from worker.model_ops.rl_alignment_training import _generate_candidate_text, _scored_seed_candidates

    class EmptyPolicyBackend:
        runtime_name = "empty-policy-runtime"

        def load_model(self, model_spec):
            return {"model_id": model_spec.model_id}

        def estimate_resident_bytes(self, model_spec) -> int:
            return 1

        def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event, execution_ext=None):
            del loaded_model, prompt, sampling, cancel_event, execution_ext
            yield RuntimeTokenEvent(text="")

    runtime = MLXTextRuntime(backend=EmptyPolicyBackend())
    loaded_model = runtime.load_model(_text_model(model_path=str(tmp_path / "base-model")))

    with pytest.raises(ModelOperationError) as generation_exc:
        _generate_candidate_text(
            runtime,
            loaded_model,
            "Generate a candidate.",
            types.SimpleNamespace(
                temperature=0.0,
                top_p=1.0,
                top_k=0,
                max_output_tokens=16,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                stop=[],
            ),
            types.SimpleNamespace(is_set=lambda: False),
        )
    assert generation_exc.value.code == "alignment_generation_failed"

    with pytest.raises(ModelOperationError) as seed_exc:
        _scored_seed_candidates(
            {
                "prompt": "Draft.",
                "candidates": [{"text": "Missing score."}, {"text": "Also missing."}],
            },
            sample_index=0,
        )
    assert seed_exc.value.details["missing_field"] == "candidate.score"


def test_alignment_rl_trace_runner_rejects_missing_alignment_config() -> None:
    from worker.model_ops.rl_alignment_training import train_alignment_rl_trace

    request = types.SimpleNamespace(config=types.SimpleNamespace(alignment=None))

    with pytest.raises(ModelOperationError) as exc:
        train_alignment_rl_trace(request)

    assert exc.value.code == "invalid_alignment_config"


def test_alignment_rl_trace_runner_rejects_unknown_algorithm(tmp_path: Path) -> None:
    from worker.model_ops.rl_alignment_training import train_alignment_rl_trace

    normalized_dataset_dir = tmp_path / "normalized"
    normalized_dataset_dir.mkdir()
    (normalized_dataset_dir / "train.jsonl").write_text(
        json.dumps({"reward_score": 1.0}) + "\n",
        encoding="utf-8",
    )
    request = types.SimpleNamespace(
        normalized_dataset_dir=normalized_dataset_dir,
        config=types.SimpleNamespace(
            alignment=types.SimpleNamespace(alignment_algorithm="ppo"),
        ),
    )

    with pytest.raises(ModelOperationError) as exc:
        train_alignment_rl_trace(request)

    assert exc.value.code == "unsupported_alignment_trainer"
    assert exc.value.details["alignment_algorithm"] == "ppo"


@pytest.mark.parametrize(
    ("file_state", "expected_message"),
    [
        ("missing", "requires train.jsonl"),
        ("invalid-json", "must contain valid JSON lines"),
        ("array-row", "rows must be JSON objects"),
        ("empty", "requires at least one scored row"),
    ],
)
def test_alignment_rl_trace_runner_rejects_invalid_training_rows(
    tmp_path: Path,
    file_state: str,
    expected_message: str,
) -> None:
    from worker.model_ops.rl_alignment_training import _load_training_rows

    train_path = tmp_path / "train.jsonl"
    if file_state == "invalid-json":
        train_path.write_text("{not-json\n", encoding="utf-8")
    elif file_state == "array-row":
        train_path.write_text("[]\n", encoding="utf-8")
    elif file_state == "empty":
        train_path.write_text("\n", encoding="utf-8")

    with pytest.raises(ModelOperationError) as exc:
        _load_training_rows(train_path)

    assert expected_message in exc.value.message


def test_alignment_rl_trace_runner_rejects_bad_scored_rows() -> None:
    from worker.model_ops.rl_alignment_training import (
        _grpo_policy_updates,
        _reward_summary,
        _rlhf_policy_updates,
        _tokens_per_second,
    )

    with pytest.raises(ModelOperationError) as grpo_exc:
        _grpo_policy_updates(
            [{"prompt": "Draft.", "candidates": [{"text": "Only.", "score": 0.1}]}],
            candidate_count=2,
        )
    assert grpo_exc.value.details["grpo_candidate_count"] == "2"

    with pytest.raises(ModelOperationError) as rlhf_exc:
        _rlhf_policy_updates([{"prompt": "Rate.", "response": "Helpful."}])
    assert rlhf_exc.value.details["missing_field"] == "reward_score"

    with pytest.raises(ModelOperationError):
        _reward_summary([])

    assert _tokens_per_second([], 0.0) == 0.0


def test_alignment_rl_trace_runner_rejects_unscored_grpo_candidates(tmp_path: Path) -> None:
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
                "prompt": "Draft two summaries.",
                "candidates": [
                    {"text": "Short summary."},
                    {"text": "Verbose summary."},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-grpo",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=normalized_dataset_dir,
        config=config,
        dataset_format="prompt_candidate",
    )

    with pytest.raises(ModelOperationError) as exc:
        mlx_lm_runner_module.MLXLMRunner().train(request)

    assert exc.value.code == "invalid_alignment_dataset"
    assert exc.value.details["alignment_algorithm"] == "grpo"
    assert exc.value.details["missing_field"] == "candidate.score"
    assert not request.adapter_output_dir.exists()


def test_mlx_lm_runner_routes_preference_training_to_preference_backend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from worker.model_ops import preference_training

    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={"training_mode": "dpo"},
        dataset_format="preference_pair",
        response_only_supported=False,
        sample_count=2,
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-dpo",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=tmp_path / "normalized",
        config=config,
        dataset_format="preference_pair",
        source_model_kind="text",
        source_model_ext={"text_family_id": "qwen"},
    )

    def fake_train_preference_native(
        observed_request: mlx_lm_runner_module.TrainingRequest,
    ) -> mlx_lm_runner_module.TrainingResult:
        assert observed_request is request
        observed_request.adapter_output_dir.mkdir(parents=True)
        weights_path = observed_request.adapter_output_dir / "adapters.safetensors"
        adapter_config_path = observed_request.adapter_output_dir / "adapter_config.json"
        weights_path.write_bytes(b"preference-adapter")
        adapter_config_path.write_text('{"fine_tune_type":"lora"}\n', encoding="utf-8")
        return mlx_lm_runner_module.TrainingResult(
            weights_path=weights_path,
            adapter_config_path=adapter_config_path,
            metrics=mlx_lm_runner_module.TrainingMetrics(
                job_duration_ms=10.0,
                tokens_seen=8,
                examples_seen=2,
                loss_final=0.2,
                loss_best=0.2,
                learning_rate_final=1e-4,
                preference_loss_final=0.2,
                chosen_logprob_mean=-1.5,
                rejected_logprob_mean=-2.0,
                chosen_rejected_margin=0.5,
                win_rate_proxy=1.0,
            ),
            execution_backend="native",
        )

    monkeypatch.setattr(
        preference_training,
        "train_preference_native",
        fake_train_preference_native,
    )

    result = mlx_lm_runner_module.MLXLMRunner().train(request)

    assert result.execution_backend == "native"
    assert result.weights_path.read_bytes() == b"preference-adapter"
    assert result.metrics.chosen_rejected_margin == pytest.approx(0.5)


def test_deterministic_lora_runner_declares_alignment_contract_support(tmp_path: Path) -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={"training_mode": "orpo"},
        dataset_format="preference_pair",
        response_only_supported=False,
        sample_count=2,
    )

    assert DeterministicLoRARunner().supports_alignment_training(config) is True


def test_training_request_deserialization_restores_alignment_config(tmp_path: Path) -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={"training_mode": "cpo"},
        dataset_format="preference_pair",
        response_only_supported=False,
        sample_count=2,
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-cpo",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=tmp_path / "normalized",
        config=config,
        dataset_format="preference_pair",
        source_model_kind="text",
        source_model_ext={"text_family_id": "qwen"},
    )

    restored = mlx_lm_runner_module._deserialize_training_request(
        mlx_lm_runner_module._serialize_training_request(request)
    )

    assert isinstance(restored.config.alignment, training_config_module.AlignmentTrainingConfig)
    assert restored.config.alignment.alignment_algorithm == "cpo"
    assert restored.config.alignment.dataset_contract == "preference_pair"
    assert restored.source_model_kind == "text"
    assert restored.source_model_ext == {"text_family_id": "qwen"}


def test_training_metrics_serializes_preference_fields(tmp_path: Path) -> None:
    metrics = mlx_lm_runner_module.TrainingMetrics(
        job_duration_ms=10.0,
        tokens_seen=4,
        examples_seen=2,
        loss_final=0.4,
        loss_best=0.3,
        learning_rate_final=1e-4,
        preference_loss_final=0.2,
        chosen_logprob_mean=-1.5,
        rejected_logprob_mean=-2.0,
        chosen_rejected_margin=0.5,
        win_rate_proxy=1.0,
    )
    result = mlx_lm_runner_module.TrainingResult(
        weights_path=tmp_path / "adapters.safetensors",
        adapter_config_path=tmp_path / "adapter_config.json",
        metrics=metrics,
        execution_backend="native",
    )

    restored = mlx_lm_runner_module._deserialize_training_result(
        mlx_lm_runner_module._serialize_training_result(result)
    )

    assert restored.metrics.preference_loss_final == pytest.approx(0.2)
    assert restored.metrics.chosen_logprob_mean == pytest.approx(-1.5)
    assert restored.metrics.rejected_logprob_mean == pytest.approx(-2.0)
    assert restored.metrics.chosen_rejected_margin == pytest.approx(0.5)
    assert restored.metrics.win_rate_proxy == pytest.approx(1.0)


def test_training_metrics_serializes_absent_preference_fields_as_null(tmp_path: Path) -> None:
    metrics = mlx_lm_runner_module.TrainingMetrics(
        job_duration_ms=10.0,
        tokens_seen=4,
        examples_seen=2,
        loss_final=0.4,
        loss_best=0.3,
        learning_rate_final=1e-4,
    )
    result = mlx_lm_runner_module.TrainingResult(
        weights_path=tmp_path / "adapters.safetensors",
        adapter_config_path=tmp_path / "adapter_config.json",
        metrics=metrics,
        execution_backend="native",
    )

    payload = mlx_lm_runner_module._serialize_training_result(result)
    restored = mlx_lm_runner_module._deserialize_training_result(payload)

    assert payload["metrics"]["preference_loss_final"] is None
    assert payload["metrics"]["win_rate_proxy"] is None
    assert restored.metrics.preference_loss_final is None
    assert restored.metrics.win_rate_proxy is None


def test_preference_training_loads_preference_pairs(tmp_path: Path) -> None:
    from worker.model_ops.preference_training import load_preference_pairs

    dataset_dir = tmp_path / "normalized"
    dataset_dir.mkdir()
    (dataset_dir / "train.jsonl").write_text(
        "\n" + json.dumps(
            {
                "prompt": "Choose.",
                "chosen": "Helpful.",
                "rejected": "Unsafe.",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    pairs = load_preference_pairs(dataset_dir)

    assert len(pairs) == 1
    assert pairs[0].prompt == "Choose."
    assert pairs[0].chosen == "Helpful."
    assert pairs[0].rejected == "Unsafe."


def test_preference_examples_seen_prefers_callback_count(tmp_path: Path) -> None:
    from worker.model_ops.preference_training import (
        PreferenceMetricsCollector,
        _preference_examples_seen,
    )

    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={"training_mode": "orpo", "batch_size": "2", "iters": "3"},
        dataset_format="preference_pair",
        response_only_supported=False,
        sample_count=6,
    )
    collector = PreferenceMetricsCollector()

    assert _preference_examples_seen(collector=collector, config=config) == 6

    collector.on_train_loss_report({"examples_seen": 5})

    assert _preference_examples_seen(collector=collector, config=config) == 5


def test_preference_training_rejects_missing_or_empty_train_file(tmp_path: Path) -> None:
    from worker.model_ops.preference_training import load_preference_pairs

    missing_dir = tmp_path / "missing"
    missing_dir.mkdir()
    with pytest.raises(ModelOperationError) as missing_exc:
        load_preference_pairs(missing_dir)

    assert missing_exc.value.code == "invalid_dataset_package"
    assert missing_exc.value.details["path"].endswith("train.jsonl")

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    (empty_dir / "train.jsonl").write_text("\n", encoding="utf-8")
    with pytest.raises(ModelOperationError) as empty_exc:
        load_preference_pairs(empty_dir)

    assert empty_exc.value.code == "invalid_dataset_package"
    assert "at least one" in empty_exc.value.message


def test_preference_training_rejects_missing_pair_fields(tmp_path: Path) -> None:
    from worker.model_ops.preference_training import load_preference_pairs

    dataset_dir = tmp_path / "normalized"
    dataset_dir.mkdir()
    (dataset_dir / "train.jsonl").write_text(
        json.dumps({"prompt": "Choose.", "chosen": "Helpful."}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ModelOperationError) as exc:
        load_preference_pairs(dataset_dir)

    assert exc.value.code == "invalid_dataset_package"
    assert exc.value.details["missing_field"] == "rejected"


def test_preference_training_resolves_default_and_configured_beta(tmp_path: Path) -> None:
    from worker.model_ops.preference_training import resolve_preference_objective

    default_config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={"training_mode": "dpo"},
        dataset_format="preference_pair",
        response_only_supported=False,
        sample_count=2,
    )
    configured_config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={
            "training_mode": "cpo",
            "kl_penalty": "0.35",
            "preference_margin_target": "0.25",
        },
        dataset_format="preference_pair",
        response_only_supported=False,
        sample_count=2,
    )

    assert resolve_preference_objective(default_config).beta == pytest.approx(0.1)
    configured = resolve_preference_objective(configured_config)
    assert configured.algorithm == "cpo"
    assert configured.beta == pytest.approx(0.35)
    assert configured.margin_target == pytest.approx(0.25)


def test_preference_training_rejects_objective_without_alignment(tmp_path: Path) -> None:
    from worker.model_ops.preference_training import resolve_preference_objective

    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={"training_mode": "lora"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )

    with pytest.raises(ModelOperationError) as exc:
        resolve_preference_objective(config)

    assert exc.value.code == "invalid_alignment_config"


@pytest.mark.parametrize(
    ("policy_margin", "reference_margin", "expected_order"),
    [
        (2.0, 0.0, "lower"),
        (-2.0, 0.0, "higher"),
    ],
)
def test_dpo_loss_value_prefers_policy_margin(
    policy_margin: float,
    reference_margin: float,
    expected_order: str,
) -> None:
    from worker.model_ops.preference_training import dpo_loss_value

    neutral = dpo_loss_value(0.0, reference_margin, beta=0.1)
    observed = dpo_loss_value(policy_margin, reference_margin, beta=0.1)

    if expected_order == "lower":
        assert observed < neutral
    else:
        assert observed > neutral


def test_orpo_and_cpo_loss_values_reward_positive_margins() -> None:
    from worker.model_ops.preference_training import cpo_loss_value, orpo_loss_value

    assert orpo_loss_value(chosen_nll=0.5, policy_margin=2.0, beta=0.1) < orpo_loss_value(
        chosen_nll=0.5,
        policy_margin=-2.0,
        beta=0.1,
    )
    assert cpo_loss_value(policy_margin=2.0, beta=0.1, margin_target=0.0) < cpo_loss_value(
        policy_margin=-2.0,
        beta=0.1,
        margin_target=0.0,
    )


def test_preference_metrics_collector_records_validation_loss() -> None:
    from worker.model_ops.preference_training import PreferenceMetricsCollector

    collector = PreferenceMetricsCollector()

    collector.on_val_loss_report({"val_loss": 0.27})

    assert collector.losses == [pytest.approx(0.27)]


def test_preference_training_mlx_loss_components_reward_chosen_sequence() -> None:
    mx = pytest.importorskip("mlx.core")
    np = pytest.importorskip("numpy")
    from worker.model_ops.preference_training import (
        PreferenceObjectiveConfig,
        make_preference_loss,
        preference_loss_components,
    )

    class StaticLogitModel:
        def __call__(self, inputs):  # noqa: ANN001
            logits = np.zeros((inputs.shape[0], inputs.shape[1], 5), dtype=np.float32)
            logits[:, :, 2] = 4.0
            logits[:, :, 3] = -4.0
            return mx.array(logits)

    class NeutralReferenceModel:
        def __call__(self, inputs):  # noqa: ANN001
            return mx.zeros((inputs.shape[0], inputs.shape[1], 5))

    chosen_batch = mx.array([[0, 2, 2]], dtype=mx.int32)
    chosen_lengths = mx.array([[1, 3]], dtype=mx.int32)
    rejected_batch = mx.array([[0, 3, 3]], dtype=mx.int32)
    rejected_lengths = mx.array([[1, 3]], dtype=mx.int32)
    objective = PreferenceObjectiveConfig(algorithm="dpo", beta=0.1)

    loss_values, token_count, chosen_logprob, rejected_logprob = preference_loss_components(
        model=StaticLogitModel(),
        chosen_batch=chosen_batch,
        chosen_lengths=chosen_lengths,
        rejected_batch=rejected_batch,
        rejected_lengths=rejected_lengths,
        objective=objective,
        reference_model=NeutralReferenceModel(),
    )
    loss, loss_token_count = make_preference_loss(
        objective,
        reference_model=NeutralReferenceModel(),
    )(
        StaticLogitModel(),
        chosen_batch,
        chosen_lengths,
        rejected_batch,
        rejected_lengths,
    )

    assert float(np.array(chosen_logprob).reshape(-1)[0]) > float(
        np.array(rejected_logprob).reshape(-1)[0]
    )
    assert float(np.array(loss_values).reshape(-1)[0]) > 0.0
    assert float(np.array(token_count).reshape(-1)[0]) == pytest.approx(4.0)
    assert float(np.array(loss).reshape(-1)[0]) == pytest.approx(
        float(np.array(loss_values).reshape(-1)[0])
    )
    assert float(np.array(loss_token_count).reshape(-1)[0]) == pytest.approx(4.0)


def test_preference_training_mlx_loss_components_reject_missing_dpo_reference() -> None:
    mx = pytest.importorskip("mlx.core")
    np = pytest.importorskip("numpy")
    from worker.model_ops.preference_training import PreferenceObjectiveConfig, preference_loss_components

    class StaticLogitModel:
        def __call__(self, inputs):  # noqa: ANN001
            return mx.array(np.zeros((inputs.shape[0], inputs.shape[1], 5), dtype=np.float32))

    with pytest.raises(ModelOperationError) as exc:
        preference_loss_components(
            model=StaticLogitModel(),
            chosen_batch=mx.array([[0, 2, 2]], dtype=mx.int32),
            chosen_lengths=mx.array([[1, 3]], dtype=mx.int32),
            rejected_batch=mx.array([[0, 3, 3]], dtype=mx.int32),
            rejected_lengths=mx.array([[1, 3]], dtype=mx.int32),
            objective=PreferenceObjectiveConfig(algorithm="dpo", beta=0.1),
            reference_model=None,
        )

    assert exc.value.code == "invalid_alignment_config"


def test_preference_training_sequence_logprobs_accepts_tuple_logits() -> None:
    mx = pytest.importorskip("mlx.core")
    np = pytest.importorskip("numpy")
    from worker.model_ops.preference_training import sequence_logprobs

    class TupleLogitModel:
        def __call__(self, inputs):  # noqa: ANN001
            logits = np.zeros((inputs.shape[0], inputs.shape[1], 5), dtype=np.float32)
            logits[:, :, 2] = 3.0
            return mx.array(logits), {"ignored": True}

    sequence_logprob, token_count, chosen_nll = sequence_logprobs(
        TupleLogitModel(),
        mx.array([[0, 2, 2]], dtype=mx.int32),
        mx.array([[1, 3]], dtype=mx.int32),
    )

    assert float(np.array(sequence_logprob).reshape(-1)[0]) < 0.0
    assert float(np.array(token_count).reshape(-1)[0]) == pytest.approx(2.0)
    assert float(np.array(chosen_nll).reshape(-1)[0]) > 0.0


@pytest.mark.parametrize("algorithm", ["dpo", "orpo", "cpo"])
def test_preference_training_evaluates_mlx_metrics_for_objectives(algorithm: str) -> None:
    mx = pytest.importorskip("mlx.core")
    np = pytest.importorskip("numpy")
    from worker.model_ops.preference_training import (
        PreferenceObjectiveConfig,
        PreferencePair,
        PreferenceTokenDataset,
        evaluate_preference_metrics,
        iterate_preference_batches,
    )

    class SimpleTokenizer:
        eos_token_id = 4

        def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
            del add_special_tokens
            return {
                "Prompt": [0],
                "Good": [2, 2],
                "Bad": [3, 3],
            }[text]

    class StaticLogitModel:
        def __call__(self, inputs):  # noqa: ANN001
            logits = np.zeros((inputs.shape[0], inputs.shape[1], 5), dtype=np.float32)
            logits[:, :, 2] = 4.0
            logits[:, :, 3] = -4.0
            return mx.array(logits)

    class NeutralReferenceModel:
        def __call__(self, inputs):  # noqa: ANN001
            return mx.zeros((inputs.shape[0], inputs.shape[1], 5))

    dataset = PreferenceTokenDataset(
        [
            PreferencePair(prompt="Prompt", chosen="Good", rejected="Bad"),
            PreferencePair(prompt="Prompt", chosen="Good", rejected="Bad"),
        ],
        SimpleTokenizer(),
    )
    batch = next(
        iterate_preference_batches(dataset, batch_size=2, max_seq_length=16)
    )
    reference_model = NeutralReferenceModel() if algorithm == "dpo" else None
    metrics = evaluate_preference_metrics(
        model=StaticLogitModel(),
        dataset=dataset,
        objective=PreferenceObjectiveConfig(algorithm=algorithm, beta=0.1),
        batch_size=2,
        max_seq_length=16,
        reference_model=reference_model,
    )

    assert batch[0].shape == batch[2].shape
    assert metrics.preference_loss_final > 0.0
    assert metrics.chosen_logprob_mean > metrics.rejected_logprob_mean
    assert metrics.chosen_rejected_margin > 0.0
    assert metrics.win_rate_proxy == pytest.approx(1.0)


def test_preference_training_iterate_batches_rejects_too_small_dataset() -> None:
    pytest.importorskip("mlx.core")
    from worker.model_ops.preference_training import (
        PreferencePair,
        PreferenceTokenDataset,
        iterate_preference_batches,
    )

    class SimpleTokenizer:
        eos_token_id = 4

        def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
            del add_special_tokens
            return {
                "Prompt": [0],
                "Good": [2],
                "Bad": [3],
            }[text]

    dataset = PreferenceTokenDataset(
        [PreferencePair(prompt="Prompt", chosen="Good", rejected="Bad")],
        SimpleTokenizer(),
    )

    with pytest.raises(ValueError, match="batch_size=2"):
        next(iterate_preference_batches(dataset, batch_size=2, max_seq_length=16))


def test_preference_training_iterate_batches_shards_comm_group_batches() -> None:
    pytest.importorskip("mlx.core")
    from worker.model_ops.preference_training import (
        PreferencePair,
        PreferenceTokenDataset,
        iterate_preference_batches,
    )

    class SimpleTokenizer:
        eos_token_id = 4

        def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
            del add_special_tokens
            suffix = int(text.rsplit("-", maxsplit=1)[-1])
            return [suffix]

    class FakeCommGroup:
        def __init__(self, *, rank: int, size: int) -> None:
            self._rank = rank
            self._size = size

        def rank(self) -> int:
            return self._rank

        def size(self) -> int:
            return self._size

    dataset = PreferenceTokenDataset(
        [
            PreferencePair(prompt="Prompt-0", chosen="Good-0", rejected="Bad-10"),
            PreferencePair(prompt="Prompt-1", chosen="Good-1", rejected="Bad-11"),
            PreferencePair(prompt="Prompt-2", chosen="Good-2", rejected="Bad-12"),
            PreferencePair(prompt="Prompt-3", chosen="Good-3", rejected="Bad-13"),
        ],
        SimpleTokenizer(),
    )

    rank_zero_batch = next(
        iterate_preference_batches(
            dataset,
            batch_size=4,
            max_seq_length=16,
            seed=0,
            comm_group=FakeCommGroup(rank=0, size=2),
        )
    )
    rank_one_batch = next(
        iterate_preference_batches(
            dataset,
            batch_size=4,
            max_seq_length=16,
            seed=0,
            comm_group=FakeCommGroup(rank=1, size=2),
        )
    )

    assert rank_zero_batch[1].tolist() == [[1, 3], [1, 3]]
    assert rank_one_batch[1].tolist() == [[1, 3], [1, 3]]
    assert rank_zero_batch[0][:, 1].tolist() == [0, 2]
    assert rank_one_batch[0][:, 1].tolist() == [1, 3]
    with pytest.raises(ValueError, match="divisible by the number of workers"):
        next(
            iterate_preference_batches(
                dataset,
                batch_size=4,
                max_seq_length=16,
                comm_group=FakeCommGroup(rank=0, size=3),
            )
        )


def test_preference_training_tokenizes_chat_template_and_text_fallbacks() -> None:
    from worker.model_ops.preference_training import PreferencePair, PreferenceTokenDataset

    class ChatTokenizer:
        eos_token_id = 9

        def apply_chat_template(self, messages, **kwargs):  # noqa: ANN001
            if kwargs.get("add_generation_prompt"):
                return [1, 2, 3]
            return [1, 2, 3, len(messages[-1]["content"])]

    class TextTokenizer:
        eos_token_id = None

        def encode(self, text: str) -> list[int]:
            return [len(text)]

    chat_dataset = PreferenceTokenDataset(
        [PreferencePair(prompt="Prompt", chosen="Good", rejected="Bad")],
        ChatTokenizer(),
    )
    text_dataset = PreferenceTokenDataset(
        [PreferencePair(prompt="Prompt", chosen="Good", rejected="Bad")],
        TextTokenizer(),
    )

    assert chat_dataset[0].chosen_tokens == [1, 2, 3, 4, 9]
    assert chat_dataset[0].chosen_offset == 3
    assert text_dataset[0].chosen_tokens == [6, 4]
    assert text_dataset[0].chosen_offset == 1


def test_train_preference_native_wires_mlx_lm_trainer_and_metrics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pytest.importorskip("mlx.core")
    from worker.model_ops import preference_training
    import mlx.optimizers as mlx_optimizers
    import mlx_lm.tuner.trainer as trainer_module
    import mlx_lm.tuner.utils as tuner_utils_module
    import mlx_lm.utils as mlx_utils_module

    class FakeModel:
        def __init__(self) -> None:
            self.layers = [object(), object()]
            self.freeze_count = 0
            self.eval_count = 0
            self.loaded_weights = ""

        def freeze(self) -> None:
            self.freeze_count += 1

        def eval(self) -> None:
            self.eval_count += 1

        def load_weights(self, path: str, strict: bool = False) -> None:
            assert strict is False
            self.loaded_weights = path

    class FakeTokenizer:
        eos_token_id = 4

        def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
            del add_special_tokens
            return {
                "Prompt": [0],
                "Good": [2, 2],
                "Bad": [3, 3],
            }[text]

    class FakeAdam:
        def __init__(self, learning_rate: float) -> None:
            self.learning_rate = learning_rate

    calls: dict[str, object] = {"load_paths": []}

    def fake_load(path: str, lazy: bool = False):  # noqa: ANN001
        assert lazy is False
        calls["load_paths"].append(path)
        return FakeModel(), FakeTokenizer()

    def fake_save_config(payload: dict[str, object], path: Path) -> None:
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    def fake_linear_to_lora_layers(
        model: FakeModel,
        num_layers: int,
        lora_parameters: dict[str, object],
        use_dora: bool = False,
    ) -> None:
        assert model.freeze_count == 1
        assert num_layers == 2
        assert lora_parameters["rank"] == 8
        assert use_dora is False
        calls["lora_converted"] = True

    def fake_train(
        *,
        model: FakeModel,
        args,
        optimizer: FakeAdam,
        train_dataset,
        val_dataset,
        loss,
        iterate_batches,
        training_callback,
    ) -> None:
        del model, optimizer, train_dataset, val_dataset, loss, iterate_batches
        Path(args.adapter_file).write_bytes(b"trained-preference-adapter")
        training_callback.on_train_loss_report(
            {
                "train_loss": 0.31,
                "learning_rate": 0.0002,
                "trained_tokens": 12,
                "trained_examples": 7,
                "tokens_per_second": 34.0,
            }
        )
        calls["trainer_args"] = args

    monkeypatch.setattr(mlx_utils_module, "load", fake_load)
    monkeypatch.setattr(mlx_utils_module, "save_config", fake_save_config)
    monkeypatch.setattr(
        tuner_utils_module,
        "linear_to_lora_layers",
        fake_linear_to_lora_layers,
    )
    monkeypatch.setattr(
        tuner_utils_module,
        "print_trainable_parameters",
        lambda model: None,
    )
    monkeypatch.setattr(trainer_module, "train", fake_train)
    monkeypatch.setattr(mlx_optimizers, "Adam", FakeAdam)
    monkeypatch.setattr(
        preference_training,
        "evaluate_preference_metrics",
        lambda **kwargs: preference_training.PreferenceMetricSnapshot(
            preference_loss_final=0.2,
            chosen_logprob_mean=-1.5,
            rejected_logprob_mean=-2.0,
            chosen_rejected_margin=0.5,
            win_rate_proxy=1.0,
        ),
    )

    dataset_dir = tmp_path / "normalized"
    dataset_dir.mkdir()
    (dataset_dir / "train.jsonl").write_text(
        json.dumps({"prompt": "Prompt", "chosen": "Good", "rejected": "Bad"}) + "\n",
        encoding="utf-8",
    )
    resume_path = tmp_path / "resume.safetensors"
    resume_path.write_bytes(b"resume")
    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={
            "training_mode": "dpo",
            "batch_size": "1",
            "iters": "1",
            "learning_rate": "0.0002",
            "reference_model_path": str(tmp_path / "reference-model"),
        },
        dataset_format="preference_pair",
        response_only_supported=False,
        sample_count=1,
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-dpo-native",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=dataset_dir,
        config=config,
        dataset_format="preference_pair",
        resume_source_path=resume_path,
    )

    result = preference_training.train_preference_native(request)

    assert calls["load_paths"] == [
        str(tmp_path / "base-model"),
        str(tmp_path / "reference-model"),
    ]
    assert calls["lora_converted"] is True
    assert calls["trainer_args"].batch_size == 1
    assert calls["trainer_args"].steps_per_eval == 0
    assert result.weights_path.read_bytes() == b"trained-preference-adapter"
    assert result.adapter_config_path.is_file()
    assert result.metrics.tokens_seen == 12
    assert result.metrics.examples_seen == 7
    assert result.metrics.learning_rate_final == pytest.approx(0.0002)
    assert result.metrics.preference_loss_final == pytest.approx(0.2)
    assert result.metrics.chosen_rejected_margin == pytest.approx(0.5)
    assert result.metrics.resume_source_path == str(resume_path)


def test_run_subprocess_extracts_terminal_structured_result_without_splitlines(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text("{}\n", encoding="utf-8")
    runner = MLXLMRunner()
    structured_payload = {"weights_path": "/tmp/adapters.safetensors", "metrics": {"loss_final": 0.1}}
    class NoSplitlinesStr(str):
        def splitlines(self, *args: object, **kwargs: object) -> list[str]:  # pragma: no cover - defensive guard
            del args, kwargs
            raise AssertionError("_run_subprocess should avoid stdout.splitlines()")

    stdout = NoSplitlinesStr(
        "noisy prefix mentioning __MELIX_MLX_RESULT__=not-a-line\n"
        "worker log\n"
        f"{mlx_lm_runner_module._RESULT_PREFIX}{json.dumps({'ignored': True})}\n"
        f"{mlx_lm_runner_module._RESULT_PREFIX}{json.dumps(structured_payload)}"
    )

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(mlx_lm_runner_module.subprocess, "run", fake_run)

    assert runner._run_subprocess("train", payload_path, error_code="backend_training_failure") == structured_payload

    metrics = TrainingMetrics(
        job_duration_ms=10.0,
        tokens_seen=4,
        examples_seen=2,
        loss_final=0.4,
        loss_best=0.3,
        learning_rate_final=1e-4,
        fatal_aware_grpo_schema_version="melix.fatal_aware_grpo.v1",
        fatal_candidate_count=1,
        selected_fatal_candidate_count=1,
        advantage_clamped_candidate_count=1,
        candidate_reward_trace_path="/tmp/candidate_reward_traces.jsonl",
        candidate_reward_trace_count=2,
        candidate_reward_trace_schema_version="melix.alignment_candidate_reward_trace.v1",
    )
    result = TrainingResult(
        weights_path=tmp_path / "adapters.safetensors",
        adapter_config_path=tmp_path / "adapter_config.json",
        metrics=metrics,
        execution_backend="native",
    )
    restored = mlx_lm_runner_module._deserialize_training_result(
        mlx_lm_runner_module._serialize_training_result(result)
    )

    assert restored.metrics.candidate_reward_trace_path == "/tmp/candidate_reward_traces.jsonl"
    assert restored.metrics.candidate_reward_trace_count == 2
    assert restored.metrics.fatal_aware_grpo_schema_version == "melix.fatal_aware_grpo.v1"
    assert restored.metrics.fatal_candidate_count == 1
    assert restored.metrics.selected_fatal_candidate_count == 1
    assert restored.metrics.advantage_clamped_candidate_count == 1
    assert (
        restored.metrics.candidate_reward_trace_schema_version
        == "melix.alignment_candidate_reward_trace.v1"
    )


def test_run_subprocess_rejects_missing_structured_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text("{}\n", encoding="utf-8")
    runner = MLXLMRunner()

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="worker log only\n", stderr="")

    monkeypatch.setattr(mlx_lm_runner_module.subprocess, "run", fake_run)

    with pytest.raises(ModelOperationError, match="structured result"):
        runner._run_subprocess("train", payload_path, error_code="backend_training_failure")


def test_extract_structured_result_payload_accepts_carriage_return_line_end() -> None:
    payload = {"manifest_path": "/tmp/manifest.json"}
    stdout = (
        "leading noise\r\n"
        f"{mlx_lm_runner_module._RESULT_PREFIX}{json.dumps(payload)}\r\n"
        "tail noise"
    )

    assert mlx_lm_runner_module._extract_structured_result_payload(stdout) == payload



def test_extract_structured_result_payload_skips_embedded_prefix_and_finds_prior_line() -> None:
    payload = {"value": 7}
    stdout = (
        f"{mlx_lm_runner_module._RESULT_PREFIX}{json.dumps(payload)}\n"
        "trailing log __MELIX_MLX_RESULT__=not-a-result-line"
    )

    assert mlx_lm_runner_module._extract_structured_result_payload(stdout) == payload


class _UnexpectedActivationRunner(MLXLMRunner):
    def activate(self, request):  # noqa: ANN001
        raise AssertionError("adapter_backed_runtime should not invoke fused activation")



def test_content_hash_streams_file_chunks_without_read_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = tmp_path / "weights-a.bin"
    second = tmp_path / "weights-b.bin"
    first.write_bytes(b"a" * (1024 * 1024 + 17))
    second.write_bytes(b"b" * (512 * 1024 + 9))

    expected = __import__("hashlib").sha256(first.read_bytes() + second.read_bytes()).hexdigest()[:16]

    def forbid_read_bytes(self: Path) -> bytes:  # pragma: no cover - exercised via monkeypatch
        raise AssertionError("_content_hash should stream via open(), not read_bytes()")

    monkeypatch.setattr(Path, "read_bytes", forbid_read_bytes)

    assert _content_hash(first, second) == expected



def test_load_manifest_payload_rejects_unreadable_and_non_object_json(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not-json}\n", encoding="utf-8")
    with pytest.raises(ModelOperationError, match="Resume manifest is unreadable"):
        _load_manifest_payload(broken)

    non_object = tmp_path / "array.json"
    non_object.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ModelOperationError, match="Resume manifest must be a JSON object"):
        _load_manifest_payload(non_object)



def test_latest_checkpoint_helpers_pick_latest_numeric_file_and_validate_errors(tmp_path: Path) -> None:
    checkpoints = tmp_path / "checkpoints"
    (checkpoints / "checkpoint-2").mkdir(parents=True)
    (checkpoints / "checkpoint-10").mkdir(parents=True)
    older = checkpoints / "checkpoint-2" / "adapters.safetensors"
    newer = checkpoints / "checkpoint-10" / "adapters.safetensors"
    older.write_bytes(b"older")
    newer.write_bytes(b"newer")

    assert _latest_checkpoint_from_directory(checkpoints) == newer.resolve()
    assert _validated_resume_path(checkpoints, source_label="unit-test") == newer.resolve()

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(ModelOperationError, match="Resume directory does not contain adapter weights"):
        _latest_checkpoint_from_directory(empty_dir)

    with pytest.raises(ModelOperationError, match="Resume source from unit-test does not exist"):
        _validated_resume_path(tmp_path / "missing.safetensors", source_label="unit-test")



def test_resolve_resume_path_from_manifest_prefers_checkpoint_and_requires_weight_entries(tmp_path: Path) -> None:
    manifest_path = tmp_path / "resume.json"
    checkpoint = tmp_path / "checkpoint-7" / "adapters.safetensors"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"checkpoint")

    resolved = _resolve_resume_path_from_manifest(
        manifest_path,
        {"latest_checkpoint_path": str(checkpoint), "weights_path": str(tmp_path / "ignored.safetensors")},
    )
    assert resolved == checkpoint.resolve()

    with pytest.raises(ModelOperationError, match="Resume manifest does not expose a checkpoint or weights path"):
        _resolve_resume_path_from_manifest(manifest_path, {})



def test_resolve_resume_context_handles_manifest_directory_and_missing_sources(tmp_path: Path) -> None:
    checkpoint = tmp_path / "run-42" / "checkpoint-3" / "adapters.safetensors"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"checkpoint")
    manifest = tmp_path / "resume.json"
    manifest.write_text(
        json.dumps({"job_id": "run-42", "latest_checkpoint_path": str(checkpoint)}) + "\n",
        encoding="utf-8",
    )

    manifest_context = _resolve_resume_context({"resume_manifest_path": str(manifest)})
    assert manifest_context == {
        "resume_source_path": checkpoint.resolve(),
        "resume_manifest_path": manifest.resolve(),
        "resume_source_job_id": "run-42",
    }

    source_adapter_context = _resolve_resume_context({"source_adapter_path": str(manifest)})
    assert source_adapter_context == manifest_context

    directory_context = _resolve_resume_context({"resume_source_path": str(checkpoint.parent.parent)})
    assert directory_context == {
        "resume_source_path": checkpoint.resolve(),
        "resume_manifest_path": None,
        "resume_source_job_id": "",
    }

    with pytest.raises(ModelOperationError, match="Resume source does not exist"):
        _resolve_resume_context({"resume_source_path": str(tmp_path / "missing")})



def test_adapter_activation_pipeline_emits_explicit_adapter_backed_runtime_load_contract(tmp_path: Path) -> None:
    weights_dir = tmp_path / "adapter-weights"
    weights_dir.mkdir(parents=True)
    manifest_path = tmp_path / "train_lora.adapter.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "source_model": "melix-test-text",
                "weights_path": str(weights_dir / "adapters.safetensors"),
                "adapter_name": "unit-adapter",
                "adapter_family": "qlora",
                "adapter_capabilities": {
                    "lora_like": True,
                    "mergeable": True,
                    "relora_compatible": True,
                    "quantized_base_supported": True,
                },
                "backend_supported": True,
                "unsupported_reason": "",
                "base_quantization_method": "quant_profile",
                "adapter_set_hash": "adapter-hash-1234",
                "job_id": "model-ops-0001",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    source_model = _text_model(model_path="mlx-community/Qwen3.5-0.8B-OptiQ-4bit", quant_profile_id="q4")
    source_model.parser_mode = "structured"
    source_model.reasoning_mode = "separate"
    source_model.tokenizer_hash = "tok-hash-a"
    source_model.ext["text_family_id"] = "qwen"

    result = AdapterActivationPipeline(runner=_UnexpectedActivationRunner()).run(
        job_id="model-ops-0002",
        request_ext={
            "artifact_path": str(manifest_path),
            "activation_mode": "adapter_backed_runtime",
            "derived_model_alias": "Runtime Alias",
        },
        source_model=source_model,
        output_dir=tmp_path / "activate",
    )

    assert result.manifest["activation_mode"] == "adapter_backed_runtime"
    # The manifest schema keeps ``activation_mode`` as the on-disk
    # authoritative signal; consumers derive the typed RuntimeMode enum at
    # registration time so the JSON format stays decoupled from proto wire
    # encoding. No "runtime_mode" int is written to disk.
    assert "runtime_mode" not in result.manifest
    assert result.manifest["adapter_manifest_path"] == str(manifest_path)
    assert result.manifest["adapter_weights_path"] == str(weights_dir / "adapters.safetensors")
    assert result.manifest["adapter_family"] == "qlora"
    assert result.manifest["adapter_capabilities"]["mergeable"] is True
    assert result.manifest["backend_supported"] is True
    assert result.manifest["unsupported_reason"] == ""
    assert result.manifest["base_quantization_method"] == "quant_profile"
    assert result.manifest["source_model_kind"] == "text"
    assert result.manifest["source_model_parser_mode"] == "structured"
    assert result.manifest["source_model_reasoning_mode"] == "separate"
    assert result.manifest["source_model_quant_profile_id"] == "q4"
    assert result.manifest["source_model_tokenizer_hash"] == "tok-hash-a"
    assert result.manifest["source_model_ext"]["text_family_id"] == "qwen"


def test_adapter_activation_pipeline_rejects_non_mergeable_fused_activation(tmp_path: Path) -> None:
    weights_dir = tmp_path / "adapter-weights"
    weights_dir.mkdir(parents=True)
    (weights_dir / "adapters.safetensors").write_bytes(b"fake-adapter")
    manifest_path = tmp_path / "train_lora.adapter.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "source_model": "melix-test-text",
                "weights_path": str(weights_dir / "adapters.safetensors"),
                "adapter_name": "fake-relora-adapter",
                "adapter_family": "fake_relora",
                "adapter_capabilities": {
                    "lora_like": True,
                    "mergeable": False,
                    "relora_compatible": True,
                    "quantized_base_supported": False,
                },
                "backend_supported": True,
                "unsupported_reason": "",
                "adapter_set_hash": "fake-relora-hash",
                "job_id": "model-ops-0003",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ModelOperationError) as exc:
        AdapterActivationPipeline(runner=_UnexpectedActivationRunner()).run(
            job_id="model-ops-0004",
            request_ext={
                "artifact_path": str(manifest_path),
                "activation_mode": "fused_derived_model",
            },
            source_model=_text_model(model_path=str(tmp_path / "base-model")),
            output_dir=tmp_path / "activate",
        )

    assert exc.value.code == "non_mergeable_adapter"
    assert exc.value.details["adapter_family"] == "fake_relora"


def test_adapter_activation_pipeline_rejects_backend_unsupported_manifest(tmp_path: Path) -> None:
    weights_dir = tmp_path / "adapter-weights"
    weights_dir.mkdir(parents=True)
    (weights_dir / "adapters.safetensors").write_bytes(b"fake-adapter")
    manifest_path = tmp_path / "train_lora.adapter.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "source_model": "melix-test-text",
                "weights_path": str(weights_dir / "adapters.safetensors"),
                "adapter_name": "unsupported-adapter",
                "adapter_family": "unsupported_adapter",
                "adapter_capabilities": {
                    "lora_like": True,
                    "mergeable": True,
                    "relora_compatible": False,
                    "quantized_base_supported": False,
                },
                "backend_supported": False,
                "unsupported_reason": "unsupported_backend",
                "adapter_set_hash": "unsupported-hash",
                "job_id": "model-ops-0005",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ModelOperationError) as exc:
        AdapterActivationPipeline(runner=_UnexpectedActivationRunner()).run(
            job_id="model-ops-0006",
            request_ext={
                "artifact_path": str(manifest_path),
                "activation_mode": "adapter_backed_runtime",
            },
            source_model=_text_model(model_path=str(tmp_path / "base-model")),
            output_dir=tmp_path / "activate",
        )

    assert exc.value.code == "unsupported_backend"
    assert exc.value.details["adapter_family"] == "unsupported_adapter"


def test_adapter_activation_manifest_helpers_preserve_legacy_defaults() -> None:
    assert adapter_activation_pipeline_module._manifest_bool({}, "backend_supported", default=True) is True
    assert (
        adapter_activation_pipeline_module._manifest_bool(
            {"backend_supported": "false"},
            "backend_supported",
            default=True,
        )
        is False
    )

    assert adapter_activation_pipeline_module._manifest_adapter_capabilities({}) == {
        "lora_like": True,
        "mergeable": True,
        "relora_compatible": True,
        "quantized_base_supported": True,
    }
    assert adapter_activation_pipeline_module._manifest_adapter_capabilities(
        {"adapter_capabilities": {"mergeable": "false"}}
    ) == {
        "lora_like": True,
        "mergeable": False,
        "relora_compatible": True,
        "quantized_base_supported": True,
    }


def test_adapter_activation_pipeline_validates_component_scope_for_vlm_adapters(tmp_path: Path) -> None:
    weights_dir = tmp_path / "adapter-weights"
    weights_dir.mkdir(parents=True)
    manifest_path = tmp_path / "train_lora.adapter.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "source_model": "melix-gemma4-vlm",
                "source_model_kind": "vlm",
                "weights_path": str(weights_dir / "adapters.safetensors"),
                "adapter_name": "gemma4-component-adapter",
                "adapter_set_hash": "gemma4-adapter-hash",
                "job_id": "model-ops-0003",
                "adapter_scope": "text_backbone",
                "training_surface": "text_backbone",
                "component_model_type": "gemma4_text",
                "component_family": "gemma",
                "component_model_path": str(tmp_path / "gemma4-vlm"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    source_model = _gemma4_vlm_model(model_path=str(tmp_path / "gemma4-vlm"))

    result = AdapterActivationPipeline(runner=_UnexpectedActivationRunner()).run(
        job_id="model-ops-0004",
        request_ext={
            "artifact_path": str(manifest_path),
            "activation_mode": "adapter_backed_runtime",
        },
        source_model=source_model,
        output_dir=tmp_path / "activate",
    )

    assert result.manifest["source_model_kind"] == "vlm"
    assert result.manifest["adapter_scope"] == "text_backbone"
    assert result.manifest["training_surface"] == "text_backbone"
    assert result.manifest["component_model_type"] == "gemma4_text"
    assert result.manifest["component_family"] == "gemma"
    assert result.manifest["component_model_path"] == str(tmp_path / "gemma4-vlm")
    assert result.manifest["derived_model_path"] == source_model.model_path

    mismatched = _gemma4_vlm_model(model_path=str(tmp_path / "gemma4-vlm"))
    mismatched.ext["melix.lora.adapter_scope"] = "vision_encoder"
    with pytest.raises(ModelOperationError) as scope_exc:
        AdapterActivationPipeline(runner=_UnexpectedActivationRunner()).run(
            job_id="model-ops-0005",
            request_ext={
                "artifact_path": str(manifest_path),
                "activation_mode": "adapter_backed_runtime",
            },
            source_model=mismatched,
            output_dir=tmp_path / "mismatch",
        )
    assert scope_exc.value.code == "activation_failure"
    assert "scope" in scope_exc.value.message

    with pytest.raises(ModelOperationError) as fused_exc:
        AdapterActivationPipeline().run(
            job_id="model-ops-0006",
            request_ext={"artifact_path": str(manifest_path)},
            source_model=source_model,
            output_dir=tmp_path / "fused",
        )
    assert fused_exc.value.code == "activation_failure"
    assert "adapter_backed_runtime" in fused_exc.value.message


def test_adapter_activation_pipeline_rejects_component_scope_metadata_mismatches(tmp_path: Path) -> None:
    weights_dir = tmp_path / "adapter-weights"
    weights_dir.mkdir(parents=True)

    def write_manifest(payload: dict[str, object]) -> Path:
        manifest_path = tmp_path / f"{payload['job_id']}.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "melix.lora_adapter_package.v1",
                    "weights_path": str(weights_dir / "adapters.safetensors"),
                    "adapter_name": "scope-mismatch",
                    "adapter_set_hash": str(payload["job_id"]),
                    **payload,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return manifest_path

    with pytest.raises(ModelOperationError) as kind_exc:
        AdapterActivationPipeline(runner=_UnexpectedActivationRunner()).run(
            job_id="activate-kind",
            request_ext={
                "artifact_path": str(
                    write_manifest(
                        {
                            "job_id": "adapter-kind",
                            "source_model": "melix-gemma4-vlm",
                            "source_model_kind": "text",
                            "adapter_scope": "text_backbone",
                            "training_surface": "text_backbone",
                        }
                    )
                ),
                "activation_mode": "adapter_backed_runtime",
            },
            source_model=_gemma4_vlm_model(model_path=str(tmp_path / "gemma4-vlm")),
            output_dir=tmp_path / "activate-kind",
        )
    assert kind_exc.value.code == "activation_failure"
    assert "kind" in kind_exc.value.message

    with pytest.raises(ModelOperationError) as text_scope_exc:
        AdapterActivationPipeline(runner=_UnexpectedActivationRunner()).run(
            job_id="activate-text-scope",
            request_ext={
                "artifact_path": str(
                    write_manifest(
                        {
                            "job_id": "adapter-text-scope",
                            "source_model": "melix-test-text",
                            "source_model_kind": "text",
                            "adapter_scope": "text_backbone",
                            "training_surface": "text_backbone",
                        }
                    )
                ),
                "activation_mode": "adapter_backed_runtime",
            },
            source_model=_text_model(model_path=str(tmp_path / "text-model")),
            output_dir=tmp_path / "activate-text-scope",
        )
    assert text_scope_exc.value.code == "activation_failure"
    assert "scope" in text_scope_exc.value.message

    with pytest.raises(ModelOperationError) as missing_scope_exc:
        AdapterActivationPipeline(runner=_UnexpectedActivationRunner()).run(
            job_id="activate-missing-scope",
            request_ext={
                "artifact_path": str(
                    write_manifest(
                        {
                            "job_id": "adapter-missing-scope",
                            "source_model": "plain-vlm",
                            "source_model_kind": "vlm",
                            "adapter_scope": "text_backbone",
                            "training_surface": "text_backbone",
                            "component_model_type": "gemma4_text",
                            "component_family": "gemma",
                        }
                    )
                ),
                "activation_mode": "adapter_backed_runtime",
            },
            source_model=common_pb2.ModelSpec(
                model_id="plain-vlm",
                model_path=str(tmp_path / "plain-vlm"),
                model_kind="vlm",
            ),
            output_dir=tmp_path / "activate-missing-scope",
        )
    assert missing_scope_exc.value.code == "activation_failure"
    assert "no component LoRA scope metadata" in missing_scope_exc.value.message

    with pytest.raises(ModelOperationError) as type_exc:
        AdapterActivationPipeline(runner=_UnexpectedActivationRunner()).run(
            job_id="activate-type",
            request_ext={
                "artifact_path": str(
                    write_manifest(
                        {
                            "job_id": "adapter-type",
                            "source_model": "melix-gemma4-vlm",
                            "source_model_kind": "vlm",
                            "adapter_scope": "text_backbone",
                            "training_surface": "text_backbone",
                            "component_model_type": "llama",
                            "component_family": "gemma",
                        }
                    )
                ),
                "activation_mode": "adapter_backed_runtime",
            },
            source_model=_gemma4_vlm_model(model_path=str(tmp_path / "gemma4-vlm")),
            output_dir=tmp_path / "activate-type",
        )
    assert type_exc.value.code == "activation_failure"
    assert "component type" in type_exc.value.message

    with pytest.raises(ModelOperationError) as family_exc:
        AdapterActivationPipeline(runner=_UnexpectedActivationRunner()).run(
            job_id="activate-family",
            request_ext={
                "artifact_path": str(
                    write_manifest(
                        {
                            "job_id": "adapter-family",
                            "source_model": "melix-gemma4-vlm",
                            "source_model_kind": "vlm",
                            "adapter_scope": "text_backbone",
                            "training_surface": "text_backbone",
                            "component_model_type": "gemma4_text",
                            "component_family": "qwen",
                        }
                    )
                ),
                "activation_mode": "adapter_backed_runtime",
            },
            source_model=_gemma4_vlm_model(model_path=str(tmp_path / "gemma4-vlm")),
            output_dir=tmp_path / "activate-family",
        )
    assert family_exc.value.code == "activation_failure"
    assert "component family" in family_exc.value.message



def test_normalize_training_config_rejects_non_text_models() -> None:
    model = common_pb2.ModelSpec(model_id="melix-embed", model_path="models/embed", model_kind="embedding")

    with pytest.raises(ModelOperationError) as exc:
        training_config_module.normalize_training_config(
            source_model=model,
            ext={},
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )

    assert exc.value.code == "unsupported_model_family"
    assert exc.value.details["model_kind"] == "embedding"

    vlm = common_pb2.ModelSpec(model_id="melix-vlm", model_path="models/plain-vlm", model_kind="vlm")
    with pytest.raises(ModelOperationError) as vlm_exc:
        training_config_module.normalize_training_config(
            source_model=vlm,
            ext={},
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )

    assert vlm_exc.value.code == "unsupported_model_family"
    assert vlm_exc.value.details["adapter_scope"] == ""


def test_normalize_training_config_accepts_gemma4_vlm_text_backbone_scope() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_gemma4_vlm_model(model_path="mlx-community/gemma-4-E4B-it-bf16"),
        ext={},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )

    assert config.family_id == "gemma"
    assert config.quantization_mode == "none"
    assert any(module.endswith(".self_attn.q_proj") for module in config.expanded_target_modules)
    assert any(module.endswith(".mlp.gate_proj") for module in config.expanded_target_modules)


def test_normalize_training_config_accepts_registry_owned_component_model_type() -> None:
    source_model = _gemma4_vlm_model(model_path="models/custom-component-vlm")
    source_model.ext["melix.lora.component_model_type"] = "custom_text_backbone"
    source_model.ext["melix.component.text_backbone.model_type"] = "custom_text_backbone"

    config = training_config_module.normalize_training_config(
        source_model=source_model,
        ext={},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )

    assert config.family_id == "gemma"
    assert any(module.endswith(".self_attn.q_proj") for module in config.expanded_target_modules)
    assert any(module.endswith(".mlp.gate_proj") for module in config.expanded_target_modules)


def test_resolve_adapter_scope_metadata_requires_validated_non_text_scope() -> None:
    source_model = common_pb2.ModelSpec(model_id="plain-vlm", model_path="models/plain-vlm", model_kind="vlm")

    with pytest.raises(AssertionError) as exc:
        _resolve_adapter_scope_metadata(source_model)

    assert "no adapter_scope" in str(exc.value)


def test_normalize_training_config_rejects_unknown_modes_and_families() -> None:
    with pytest.raises(ModelOperationError) as mode_exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(),
            ext={"training_mode": "mystery"},
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )
    assert mode_exc.value.code == "unsupported_training_mode"

    with pytest.raises(ModelOperationError) as family_exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(family_id="unknown-family"),
            ext={},
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )
    assert family_exc.value.code == "unsupported_model_family"


def test_normalize_training_config_rejects_response_only_for_unsupported_shapes() -> None:
    with pytest.raises(ModelOperationError) as exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(),
            ext={"response_only": "true"},
            dataset_format="text_completion",
            response_only_supported=False,
            sample_count=1,
        )

    assert exc.value.code == "invalid_dataset_package"


def test_training_config_helpers_cover_family_and_validation_branches() -> None:
    mixtral = training_config_module.normalize_training_config(
        source_model=_text_model(model_path="models/mixtral-8x7b", quant_profile_id="q4"),
        ext={"training_mode": "qlora", "hf_valid_split": "validation", "derived_model_alias": "alias-a"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
        validation_sample_count=1,
    )
    fallback = training_config_module.normalize_training_config(
        source_model=_text_model(model_path="models/plain-generic"),
        ext={},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=1,
    )

    assert mixtral.family_id == "mixtral"
    assert mixtral.quantization_mode == "quantized_base"
    assert mixtral.validation_strategy == "hf_split"
    assert mixtral.desired_derived_model_alias == "alias-a"
    assert fallback.family_id == "llama"
    assert training_config_module._backend_target_modules(["custom.module"]) == ["custom.module"]


def test_training_config_applies_named_presets_and_allows_explicit_overrides() -> None:
    balanced = training_config_module.normalize_training_config(
        source_model=_text_model(model_path="mlx-community/Qwen3.5-0.8B-OptiQ-4bit", quant_profile_id="q4"),
        ext={"preset_id": "balanced_adapter", "training_mode": "qlora", "rank": "24"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=4,
    )

    assert balanced.preset_id == "balanced_adapter"
    assert balanced.preset_title == "Balanced Adapter"
    assert balanced.rank == 24
    assert balanced.alpha == 32.0
    assert balanced.dropout == 0.05
    assert balanced.gradient_checkpointing is True
    assert balanced.batch_size == 2
    assert balanced.epochs == 2
    assert balanced.learning_rate == 1e-4

    with pytest.raises(ModelOperationError) as unknown_preset:
        training_config_module.normalize_training_config(
            source_model=_text_model(),
            ext={"preset_id": "mystery"},
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )
    assert unknown_preset.value.code == "invalid_training_preset"


def test_training_config_defaults_gradient_accumulation_to_one() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(),
        ext={},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=1,
    )

    assert config.gradient_accumulation == 1


def test_training_config_accepts_explicit_gradient_accumulation() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(),
        ext={"gradient_accumulation": "4"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )

    assert config.gradient_accumulation == 4


@pytest.mark.parametrize("bad_value", ["0", "-1"])
def test_training_config_rejects_non_positive_gradient_accumulation(bad_value: str) -> None:
    with pytest.raises(ModelOperationError) as exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(),
            ext={"gradient_accumulation": bad_value},
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )

    assert exc.value.code == "invalid_argument"
    assert "gradient_accumulation" in (exc.value.message or "")


def test_training_config_rejects_non_numeric_gradient_accumulation() -> None:
    with pytest.raises(ModelOperationError) as exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(),
            ext={"gradient_accumulation": "abc"},
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )

    assert exc.value.code == "invalid_argument"
    assert exc.value.message == "gradient_accumulation must be an integer."
    assert exc.value.details["field"] == "gradient_accumulation"
    assert exc.value.details["raw_value"] == "abc"


def test_training_config_defaults_chunked_training_off() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(),
        ext={},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=1,
    )

    assert config.chunked_training is False
    assert config.chunk_size == config.max_seq_length


def test_training_config_accepts_chunked_training_with_explicit_chunk_size() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(),
        ext={
            "chunked_training": "true",
            "chunk_size": "2048",
            "max_seq_length": "4096",
        },
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=1,
    )

    assert config.chunked_training is True
    assert config.chunk_size == 2048
    assert config.max_seq_length == 4096


def test_training_config_rejects_chunk_size_larger_than_max_seq_length() -> None:
    with pytest.raises(ModelOperationError) as exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(),
            ext={
                "chunked_training": "true",
                "chunk_size": "8192",
                "max_seq_length": "4096",
            },
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )

    assert exc.value.code == "invalid_chunk_size"


def test_training_config_rejects_chunk_size_below_minimum() -> None:
    with pytest.raises(ModelOperationError) as exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(),
            ext={"chunk_size": "256"},
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )

    assert exc.value.code == "invalid_chunk_size"
    assert "chunk_size" in (exc.value.message or "")


def test_mlx_lora_namespace_forwards_gradient_accumulation() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(),
        ext={"gradient_accumulation": "3"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-accum",
        base_model_id="melix-dev-text",
        model_path=Path("/tmp/dummy-model"),
        model_revision="main",
        adapter_output_dir=Path("/tmp/dummy-adapter"),
        normalized_dataset_dir=Path("/tmp/dummy-dataset"),
        config=config,
        dataset_format="chat_messages",
    )

    namespace = mlx_lm_runner_module._mlx_lora_namespace(request)

    assert namespace.grad_accumulation_steps == 3
    assert namespace.batch_size == config.batch_size


def test_training_config_caps_computed_iters_with_max_steps() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path="mlx-community/Qwen3.5-0.8B-OptiQ-4bit", quant_profile_id="q4"),
        ext={
            "training_mode": "qlora",
            "batch_size": "1",
            "epochs": "4",
            "max_steps": "2",
            "hf_valid_split": "validation",
        },
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=6,
        validation_sample_count=1,
    )

    assert config.iters == 2
    assert config.steps_per_report == 2
    assert config.steps_per_eval == 2
    assert config.steps_per_save == 2


def test_training_config_resolves_qwen_gemma_and_kimi_families() -> None:
    qwen = training_config_module.normalize_training_config(
        source_model=_text_model(
            model_path="mlx-community/Qwen3.5-0.8B-Instruct-4bit",
            quant_profile_id="q4",
        ),
        ext={"training_mode": "qlora"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )
    gemma = training_config_module.normalize_training_config(
        source_model=_text_model(model_path="unsloth/gemma-3-4b-it"),
        ext={},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )
    kimi = training_config_module.normalize_training_config(
        source_model=_text_model(
            model_path="mlx-community/kimi-k2-instruct-4bit",
            quant_profile_id="q4",
        ),
        ext={"training_mode": "qlora"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )

    assert qwen.family_id == "qwen"
    assert gemma.family_id == "gemma"
    assert kimi.family_id == "kimi"
    assert qwen.quantization_mode == "quantized_base"
    assert kimi.quantization_mode == "quantized_base"
    assert any(module.endswith(".self_attn.q_proj") for module in qwen.expanded_target_modules)
    assert any(module.endswith(".mlp.gate_proj") for module in gemma.expanded_target_modules)
    assert any(module.endswith(".mlp.down_proj") for module in kimi.expanded_target_modules)


def test_training_config_scalar_helpers_reject_invalid_values() -> None:
    with pytest.raises(ModelOperationError):
        training_config_module._int_value("0", default=1, minimum=1, field_name="rank")
    with pytest.raises(ModelOperationError):
        training_config_module._float_value("-1", default=0.0, minimum=0.0, field_name="dropout")


@pytest.mark.parametrize(
    ("manifest_payload", "sample_lines", "expected_code"),
    [
        (None, ["{not-json"], "invalid_dataset_package"),
        ({"schema_version": "melix.training_dataset_package.v1"}, [json.dumps({"text": "hello"})], "invalid_dataset_package"),
        (
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "bad-format",
                "format": "unknown",
                "sample_count": 1,
                "version": "1",
            },
            [json.dumps({"text": "hello"})],
            "invalid_dataset_package",
        ),
        (
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "mismatch",
                "format": "text_completion",
                "sample_count": 2,
                "version": "1",
            },
            [json.dumps({"text": "hello"})],
            "invalid_dataset_package",
        ),
    ],
)
def test_load_training_dataset_package_rejects_manifest_and_sample_errors(
    tmp_path: Path,
    manifest_payload: dict[str, object] | None,
    sample_lines: list[str],
    expected_code: str,
) -> None:
    package_dir = tmp_path / "dataset"
    package_dir.mkdir(parents=True, exist_ok=True)
    if manifest_payload is None:
        (package_dir / "manifest.json").write_text("{not-json", encoding="utf-8")
    else:
        (package_dir / "manifest.json").write_text(json.dumps(manifest_payload) + "\n", encoding="utf-8")
    (package_dir / "samples.jsonl").write_text("\n".join(sample_lines) + "\n", encoding="utf-8")

    with pytest.raises(ModelOperationError) as exc:
        load_training_dataset_package(str(package_dir))

    assert exc.value.code == expected_code


def test_load_training_dataset_package_rejects_empty_and_invalid_validation_data(tmp_path: Path) -> None:
    empty_package = _write_dataset_package(
        tmp_path / "empty",
        manifest_payload={
            "schema_version": "melix.training_dataset_package.v1",
            "dataset_id": "empty",
            "format": "text_completion",
            "sample_count": 1,
            "version": "1",
        },
        sample_lines=[""],
    )
    with pytest.raises(ModelOperationError) as empty_exc:
        load_training_dataset_package(str(empty_package))
    assert empty_exc.value.code == "invalid_dataset_package"

    invalid_valid = _write_dataset_package(
        tmp_path / "invalid-valid",
        valid_lines=["{not-json"],
    )
    with pytest.raises(ModelOperationError) as valid_exc:
        load_training_dataset_package(str(invalid_valid))
    assert valid_exc.value.code == "invalid_dataset_package"


@pytest.mark.parametrize(
    "sample",
    [
        "not-a-dict",
        {"messages": []},
        {"messages": ["bad"]},
        {"messages": [{"role": "invalid", "content": "bad"}]},
        {
            "messages": [
                {"role": "user", "content": "a"},
                {"role": "user", "content": "b"},
                {"role": "assistant", "content": "c"},
            ]
        },
        {"messages": [{"role": "user", "content": "a"}]},
    ],
)
def test_normalize_sample_rejects_invalid_chat_shapes(sample: object) -> None:
    with pytest.raises(ModelOperationError):
        training_dataset_module._normalize_sample(
            sample,
            format_name="chat_messages",
            max_characters_per_sample=0,
        )


def test_normalize_sample_covers_prompt_text_and_tool_paths() -> None:
    prompt_completion = training_dataset_module._normalize_sample(
        {"prompt": "abcdef", "completion": "uvwxyz"},
        format_name="prompt_completion",
        max_characters_per_sample=3,
    )
    with_tools = training_dataset_module._normalize_sample(
        {
            "messages": [
                {"role": "user", "content": "abcdef"},
                {"role": "assistant", "content": "uvwxyz"},
            ],
            "tools": [{"name": "search"}],
        },
        format_name="chat_messages",
        max_characters_per_sample=3,
    )
    with pytest.raises(ModelOperationError):
        training_dataset_module._normalize_sample(
            {"prompt": "", "completion": "x"},
            format_name="prompt_completion",
            max_characters_per_sample=0,
        )
    with pytest.raises(ModelOperationError):
        training_dataset_module._normalize_sample(
            {"text": ""},
            format_name="text_completion",
            max_characters_per_sample=0,
        )

    assert prompt_completion == {"prompt": "abc", "completion": "uvw"}
    assert with_tools["tools"] == [{"name": "search"}]
    assert with_tools["messages"][0]["content"] == "abc"
    assert training_dataset_module._truncate_text("abcdef", 2) == "ab"


def test_materialize_hf_training_dataset_rejects_empty_validation_split(tmp_path: Path) -> None:
    reference = HFDatasetReference(
        dataset_path="melix/demo-hf",
        dataset_name="default",
        dataset_revision="main",
        train_split="train",
        chat_feature="",
        prompt_feature="",
        completion_feature="",
        text_feature="text",
        valid_split="validation",
    )

    def fetcher(endpoint: str, params: dict[str, str]) -> dict[str, object]:
        if endpoint == "rows" and params["split"] == "validation":
            return {"rows": []}
        if endpoint == "rows":
            return {"rows": [{"row": {"text": "hello"}}]}
        return {"splits": [{"split": "train", "config": "default"}]}

    with pytest.raises(ModelOperationError) as exc:
        materialize_hf_training_dataset_package(
            reference,
            cache_root=tmp_path / "datasets",
            fetch_json=fetcher,
        )

    assert exc.value.code == "hf_dataset_fetch_failed"


def test_materialize_hf_training_dataset_writes_validation_split_jsonl(tmp_path: Path) -> None:
    reference = HFDatasetReference(
        dataset_path="melix/demo-hf",
        dataset_name="default",
        dataset_revision="main",
        train_split="train",
        chat_feature="",
        prompt_feature="p",
        completion_feature="c",
        text_feature="",
        valid_split="validation",
    )

    def fetcher(endpoint: str, params: dict[str, str]) -> dict[str, object]:
        if endpoint != "rows":
            return {"splits": [{"split": "train", "config": "default"}]}
        if params["split"] == "validation":
            return {"rows": [{"row": {"p": "holdout", "c": "answer"}}]}
        return {"rows": [{"row": {"p": "hello", "c": "world"}}]}

    package = materialize_hf_training_dataset_package(
        reference,
        cache_root=tmp_path / "datasets",
        fetch_json=fetcher,
    )

    assert (package.package_path / "samples.jsonl").read_text(encoding="utf-8") == (
        '{"prompt": "hello", "completion": "world"}\n'
    )
    assert (package.package_path / "valid.jsonl").read_text(encoding="utf-8") == (
        '{"prompt": "holdout", "completion": "answer"}\n'
    )


def test_hf_dataset_helpers_cover_paging_and_direct_chat_paths(tmp_path: Path) -> None:
    reference = HFDatasetReference(
        dataset_path="melix/demo-hf",
        dataset_name="default",
        dataset_revision="main",
        train_split="train",
        chat_feature="messages",
        prompt_feature="",
        completion_feature="",
        text_feature="",
    )

    config = training_dataset_module._resolve_hf_dataset_name(
        reference,
        lambda endpoint, params: {"splits": ["bad", {"split": "train", "config": "default"}]},
    )
    assert config == "default"

    calls: list[int] = []

    def paged_fetcher(endpoint: str, params: dict[str, str]) -> dict[str, object]:
        calls.append(int(params["offset"]))
        if params["offset"] == "0":
            return {"rows": [{"row": {"text": f"value-{index}"}} for index in range(100)]}
        return {"rows": []}

    rows = training_dataset_module._fetch_hf_dataset_rows(
        HFDatasetReference(
            dataset_path="melix/demo-hf",
            dataset_name="default",
            dataset_revision="main",
            train_split="train",
            chat_feature="",
            prompt_feature="",
            completion_feature="",
            text_feature="text",
        ),
        paged_fetcher,
    )
    assert len(rows) == 100
    assert calls == [0, 100]

    assert training_dataset_module._infer_hf_dataset_format(reference, [{"messages": []}]) == "chat_messages"
    assert training_dataset_module._infer_hf_dataset_format(
        HFDatasetReference(
            dataset_path="melix/demo-hf",
            dataset_name="default",
            dataset_revision="main",
            train_split="train",
            chat_feature="",
            prompt_feature="p",
            completion_feature="c",
            text_feature="",
        ),
        [{"p": "hi", "c": "there"}],
    ) == "prompt_completion"
    assert training_dataset_module._map_hf_row_to_training_sample(
        {"messages": [{"role": "user", "content": "hello"}]},
        "chat_messages",
        reference,
    ) == {"messages": [{"role": "user", "content": "hello"}]}


def test_misc_lora_helpers_cover_int_ext_and_cached_valid_split(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "hf_dataset_name": "default",
                "hf_dataset_revision": "main",
                "hf_train_split": "train",
                "hf_valid_split": "validation",
            }
        ),
        encoding="utf-8",
    )
    reference = HFDatasetReference(
        dataset_path="melix/demo-hf",
        dataset_name="",
        dataset_revision="old",
        train_split="old-train",
        chat_feature="",
        prompt_feature="",
        completion_feature="",
        text_feature="text",
    )

    restored = training_dataset_module._reference_from_cached_manifest(reference, manifest_path)

    assert restored.valid_split == "validation"
    assert _int_ext({"sample_limit": "7"}, "sample_limit") == 7
    assert _int_ext({}, "sample_limit") == 0


def test_mlx_lm_runner_train_native_collects_checkpoint_throughput_and_peak_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mlx_pkg = types.ModuleType("mlx")
    fake_mlx_pkg.__path__ = []
    fake_mlx_core = types.ModuleType("mlx.core")
    reset_calls: list[str] = []

    class FakeMetal:
        @staticmethod
        def reset_peak_memory() -> None:
            reset_calls.append("reset")

        @staticmethod
        def get_peak_memory() -> float:
            return float(3 * 1024**3)

    fake_mlx_core.metal = FakeMetal()
    fake_mlx_pkg.core = fake_mlx_core
    monkeypatch.setitem(sys.modules, "mlx", fake_mlx_pkg)
    monkeypatch.setitem(sys.modules, "mlx.core", fake_mlx_core)

    fake_mlx_lm = types.ModuleType("mlx_lm")
    fake_mlx_lm.__path__ = []
    fake_lora = types.ModuleType("mlx_lm.lora")
    fake_callbacks = types.ModuleType("mlx_lm.tuner.callbacks")
    fake_datasets = types.ModuleType("mlx_lm.tuner.datasets")
    fake_utils = types.ModuleType("mlx_lm.utils")

    class FakeTrainingCallback:
        pass

    def fake_load(model_source: str, *, lazy: bool = False):
        assert model_source == str(tmp_path / "base-model")
        assert lazy is False
        return object(), object()

    def fake_load_local_dataset(dataset_dir: Path, tokenizer, args):
        _ = tokenizer
        assert dataset_dir == tmp_path / "normalized"
        assert args.adapter_path == str(tmp_path / "adapter-output")
        return ["train"], ["valid"], None

    def fake_train_model(args, model, train_set, valid_set, training_callback) -> None:
        _ = model
        assert train_set == ["train"]
        assert valid_set == ["valid"]
        training_callback.on_train_loss_report(
            {
                "train_loss": 0.8,
                "learning_rate": 1e-4,
                "trained_tokens": 120,
            }
        )
        training_callback.on_val_loss_report({"val_loss": 0.2})
        checkpoint_root = Path(args.adapter_path)
        checkpoint_root.mkdir(parents=True, exist_ok=True)
        (checkpoint_root / "checkpoint-1").mkdir(parents=True, exist_ok=True)
        (checkpoint_root / "checkpoint-1" / "weights.safetensors").write_text("a", encoding="utf-8")
        (checkpoint_root / "checkpoint-2.safetensors").write_text("b", encoding="utf-8")

    fake_lora.train_model = fake_train_model
    fake_callbacks.TrainingCallback = FakeTrainingCallback
    fake_datasets.load_local_dataset = fake_load_local_dataset
    fake_utils.load = fake_load
    monkeypatch.setitem(sys.modules, "mlx_lm", fake_mlx_lm)
    monkeypatch.setitem(sys.modules, "mlx_lm.lora", fake_lora)
    monkeypatch.setitem(sys.modules, "mlx_lm.tuner.callbacks", fake_callbacks)
    monkeypatch.setitem(sys.modules, "mlx_lm.tuner.datasets", fake_datasets)
    monkeypatch.setitem(sys.modules, "mlx_lm.utils", fake_utils)

    perf_counter_values = iter([10.0, 12.0])
    monkeypatch.setattr(
        mlx_lm_runner_module.time,
        "perf_counter",
        lambda: next(perf_counter_values),
    )

    config = training_config_module.normalize_training_config(
        source_model=_text_model(
            model_path=str(tmp_path / "base-model"),
            quant_profile_id="q4",
        ),
        ext={"training_mode": "qlora"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=4,
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-real",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=tmp_path / "normalized",
        config=config,
        dataset_format="chat_messages",
    )

    result = mlx_lm_runner_module.MLXLMRunner().train_native(request)

    assert reset_calls == ["reset"]
    assert result.metrics.loss_final == pytest.approx(0.2)
    assert result.metrics.loss_best == pytest.approx(0.2)
    assert result.metrics.learning_rate_final == pytest.approx(1e-4)
    assert result.metrics.checkpoint_count == 2
    assert result.metrics.resume_ready is True
    assert result.metrics.tokens_per_second == pytest.approx(60.0)
    assert result.metrics.peak_memory_gb == pytest.approx(3.0)


def test_mlx_lm_runner_train_native_fails_when_response_only_labels_are_truncated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mlx_lm = types.ModuleType("mlx_lm")
    fake_mlx_lm.__path__ = []
    fake_lora = types.ModuleType("mlx_lm.lora")
    fake_callbacks = types.ModuleType("mlx_lm.tuner.callbacks")
    fake_datasets = types.ModuleType("mlx_lm.tuner.datasets")
    fake_utils = types.ModuleType("mlx_lm.utils")
    train_calls: list[str] = []

    class FakeTrainingCallback:
        pass

    class FakeTrainSet:
        def __len__(self) -> int:
            return 2

        def __getitem__(self, index: int) -> dict[str, int]:
            return {"index": index}

        def process(self, sample: dict[str, int]) -> tuple[list[int], int]:
            _ = sample
            return list(range(10)), 8

    def fake_load(model_source: str, *, lazy: bool = False):
        _ = model_source, lazy
        return object(), object()

    def fake_load_local_dataset(dataset_dir: Path, tokenizer, args):
        _ = dataset_dir, tokenizer, args
        return FakeTrainSet(), [], None

    def fake_train_model(args, model, train_set, valid_set, training_callback) -> None:
        _ = args, model, train_set, valid_set, training_callback
        train_calls.append("called")

    fake_lora.train_model = fake_train_model
    fake_callbacks.TrainingCallback = FakeTrainingCallback
    fake_datasets.load_local_dataset = fake_load_local_dataset
    fake_utils.load = fake_load
    monkeypatch.setitem(sys.modules, "mlx_lm", fake_mlx_lm)
    monkeypatch.setitem(sys.modules, "mlx_lm.lora", fake_lora)
    monkeypatch.setitem(sys.modules, "mlx_lm.tuner.callbacks", fake_callbacks)
    monkeypatch.setitem(sys.modules, "mlx_lm.tuner.datasets", fake_datasets)
    monkeypatch.setitem(sys.modules, "mlx_lm.utils", fake_utils)

    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={"max_seq_length": "8", "response_only": "true", "mask_prompt": "true"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-truncated-labels",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=tmp_path / "normalized",
        config=config,
        dataset_format="chat_messages",
    )

    with pytest.raises(ModelOperationError) as exc:
        mlx_lm_runner_module.MLXLMRunner().train_native(request)

    assert exc.value.code == "response_only_labels_truncated"
    assert exc.value.details["max_seq_length"] == "8"
    assert exc.value.details["response_only_boundary_sample_count"] == "2"
    assert exc.value.details["response_only_trainable_response_token_count"] == "0"
    assert train_calls == []


def test_mlx_lm_runner_train_native_retries_quantized_load_with_relaxed_strictness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mlx_lm = types.ModuleType("mlx_lm")
    fake_mlx_lm.__path__ = []
    fake_lora = types.ModuleType("mlx_lm.lora")
    fake_callbacks = types.ModuleType("mlx_lm.tuner.callbacks")
    fake_datasets = types.ModuleType("mlx_lm.tuner.datasets")
    fake_utils = types.ModuleType("mlx_lm.utils")
    calls: list[tuple[str, object]] = []
    fake_model = object()
    fake_tokenizer = object()

    class FakeTrainingCallback:
        pass

    def fake_load(model_source: str, *, lazy: bool = False):
        calls.append(("load", (model_source, lazy)))
        raise ValueError("Received 126 parameters not in model: language_model.model.layers.24.self_attn.k_proj.biases")

    def fake_download(model_source: str, revision: str | None = None):
        calls.append(("download", (model_source, revision)))
        return tmp_path / "downloaded-model"

    def fake_load_model(model_path: Path, *, lazy: bool = False, strict: bool = True):
        calls.append(("load_model", (model_path, lazy, strict)))
        return fake_model, {"eos_token_id": [1, 2]}

    def fake_load_tokenizer(model_path: Path, tokenizer_config_extra=None, eos_token_ids=None):
        calls.append(("load_tokenizer", (model_path, tokenizer_config_extra, eos_token_ids)))
        return fake_tokenizer

    def fake_load_local_dataset(dataset_dir: Path, tokenizer, args):
        _ = args
        calls.append(("dataset", (dataset_dir, tokenizer)))
        return ["train"], [], None

    def fake_train_model(args, model, train_set, valid_set, training_callback) -> None:
        _ = args
        assert model is fake_model
        assert train_set == ["train"]
        assert valid_set == []
        training_callback.on_train_loss_report(
            {
                "train_loss": 0.7,
                "learning_rate": 2e-4,
                "trained_tokens": 10,
            }
        )

    fake_lora.train_model = fake_train_model
    fake_callbacks.TrainingCallback = FakeTrainingCallback
    fake_datasets.load_local_dataset = fake_load_local_dataset
    fake_utils.load = fake_load
    fake_utils._download = fake_download
    fake_utils.load_model = fake_load_model
    fake_utils.load_tokenizer = fake_load_tokenizer
    monkeypatch.setitem(sys.modules, "mlx_lm", fake_mlx_lm)
    monkeypatch.setitem(sys.modules, "mlx_lm.lora", fake_lora)
    monkeypatch.setitem(sys.modules, "mlx_lm.tuner.callbacks", fake_callbacks)
    monkeypatch.setitem(sys.modules, "mlx_lm.tuner.datasets", fake_datasets)
    monkeypatch.setitem(sys.modules, "mlx_lm.utils", fake_utils)

    config = training_config_module.normalize_training_config(
        source_model=_text_model(
            model_path="unsloth/gemma-4-E4B-it-MLX-8bit",
            quant_profile_id="8bit",
        ),
        ext={"training_mode": "qlora"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-quantized-retry",
        base_model_id="gemma4-8bit",
        model_path=Path("unsloth/gemma-4-E4B-it-MLX-8bit"),
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=tmp_path / "normalized",
        config=config,
        dataset_format="chat_messages",
    )

    result = mlx_lm_runner_module.MLXLMRunner().train_native(request)

    assert result.metrics.loss_final == pytest.approx(0.7)
    assert calls[:4] == [
        ("load", ("unsloth/gemma-4-E4B-it-MLX-8bit", False)),
        ("download", ("unsloth/gemma-4-E4B-it-MLX-8bit", "main")),
        ("load_model", (tmp_path / "downloaded-model", False, False)),
        ("load_tokenizer", (tmp_path / "downloaded-model", None, [1, 2])),
    ]
    assert calls[4] == ("dataset", (tmp_path / "normalized", fake_tokenizer))


def test_mlx_lm_runner_quantized_load_retry_preserves_unrelated_value_errors(
    tmp_path: Path,
) -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-plain-load-failure",
        base_model_id="plain",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=tmp_path / "normalized",
        config=config,
        dataset_format="chat_messages",
    )

    def fake_load(_model_source: str, *, lazy: bool = False):
        _ = lazy
        raise ValueError("Tokenizer config is invalid.")

    with pytest.raises(ValueError, match="Tokenizer config is invalid"):
        mlx_lm_runner_module._load_lora_training_model(request, fake_load)


@pytest.mark.parametrize("weights_path_value", [None, ""])
def test_adapter_backed_runtime_manifest_requires_adapter_weights_path(
    tmp_path: Path,
    weights_path_value: object,
) -> None:
    adapter_manifest_path = tmp_path / "train_lora.adapter.json"
    adapter_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "source_model": "melix-test-text",
                "adapter_set_hash": "adapter-alpha",
                "adapter_name": "demo-adapter",
                "weights_path": weights_path_value,
            }
        ) + "\n",
        encoding="utf-8",
    )

    pipeline = AdapterActivationPipeline()

    with pytest.raises(ModelOperationError) as exc:
        pipeline.run(
            job_id="activate-1",
            request_ext={
                "artifact_path": str(adapter_manifest_path),
                "activation_mode": "adapter_backed_runtime",
            },
            source_model=_text_model(model_path=str(tmp_path / "base-model")),
            output_dir=tmp_path / "activate",
        )

    assert exc.value.code == "activation_failure"
    assert "weights_path" in exc.value.message


def test_adapter_backed_runtime_activation_writes_explicit_runtime_contract(tmp_path: Path) -> None:
    adapter_weights_path = tmp_path / "weights" / "adapters.safetensors"
    adapter_weights_path.parent.mkdir(parents=True, exist_ok=True)
    adapter_weights_path.write_text("adapter", encoding="utf-8")
    adapter_manifest_path = tmp_path / "train_lora.adapter.json"
    adapter_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "source_model": "melix-test-text",
                "adapter_set_hash": "adapter-beta",
                "adapter_name": "demo-adapter",
                "weights_path": str(adapter_weights_path),
                "desired_derived_model_alias": "Demo Alias",
                "training_mode": "qlora",
                "quantization_mode": "quantized_base",
                "target_modules": ["model.layers.0.self_attn.q_proj"],
            }
        ) + "\n",
        encoding="utf-8",
    )

    class GuardRunner:
        def activate(self, request) -> None:  # pragma: no cover - should never be called
            raise AssertionError(f"unexpected fused activation request: {request}")

    pipeline = AdapterActivationPipeline(runner=GuardRunner())
    result = pipeline.run(
        job_id="activate-2",
        request_ext={
            "artifact_path": str(adapter_manifest_path),
            "activation_mode": "adapter_backed_runtime",
        },
        source_model=_text_model(
            model_path=str(tmp_path / "base-model"),
            quant_profile_id="q4",
        ),
        output_dir=tmp_path / "activate",
    )

    assert result.manifest["schema_version"] == "melix.derived_text_model.v1"
    assert result.manifest["activation_mode"] == "adapter_backed_runtime"
    assert result.manifest["activation_backend"] == "internal"
    assert result.manifest["adapter_manifest_path"] == str(adapter_manifest_path)
    assert result.manifest["adapter_weights_path"] == str(adapter_weights_path)
    assert result.manifest["derived_model_path"] == str(tmp_path / "base-model")
    assert result.manifest["derived_model_alias"] == "Demo Alias"
    assert result.manifest["adapter_runtime.switch_mode"] == "base_reuse_adapter_swap"
    assert result.manifest["adapter_runtime.sharing_policy"] == "shared_base_isolated_adapter"
    assert result.manifest["adapter_runtime.compatibility_status"] == "compatible"
    assert len(result.manifest["adapter_runtime.base_reuse_key"]) == 64
    assert len(result.manifest["adapter_runtime.adapter_isolation_key"]) == 64
    assert result.manifest["quantized_base_detected"] is True
    assert result.manifest["quantized_base_kind"] == "q4"
    assert result.manifest["quantization_profile_id"] == "q4"
    assert result.manifest["quantized_base_evidence_source"] == "quant_profile_id"
    assert result.manifest["qlora_compatibility_status"] == "compatible"
    assert result.manifest["quantized_target_module_guard"] == "accepted"
    assert result.manifest_path.exists()


def test_adapter_backed_runtime_activation_tolerates_legacy_scalar_targets(tmp_path: Path) -> None:
    adapter_weights_path = tmp_path / "weights" / "adapters.safetensors"
    adapter_weights_path.parent.mkdir(parents=True, exist_ok=True)
    adapter_weights_path.write_text("adapter", encoding="utf-8")
    adapter_manifest_path = tmp_path / "train_lora.adapter.json"
    adapter_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "source_model": "melix-test-text",
                "adapter_set_hash": "adapter-legacy",
                "adapter_name": "legacy-adapter",
                "weights_path": str(adapter_weights_path),
                "training_mode": "qlora",
                "quantization_mode": "quantized_base",
                "target_modules": "model.layers.0.self_attn.q_proj",
            }
        ) + "\n",
        encoding="utf-8",
    )

    result = AdapterActivationPipeline().run(
        job_id="activate-legacy",
        request_ext={
            "artifact_path": str(adapter_manifest_path),
            "activation_mode": "adapter_backed_runtime",
        },
        source_model=_text_model(
            model_path=str(tmp_path / "base-model"),
            quant_profile_id="q4",
        ),
        output_dir=tmp_path / "activate",
    )

    assert result.manifest["quantized_target_module_guard"] == "accepted"


def test_adapter_backed_runtime_activation_normalizes_legacy_csv_targets(tmp_path: Path) -> None:
    adapter_weights_path = tmp_path / "weights" / "adapters.safetensors"
    adapter_weights_path.parent.mkdir(parents=True, exist_ok=True)
    adapter_weights_path.write_text("adapter", encoding="utf-8")
    adapter_manifest_path = tmp_path / "train_lora.adapter.json"
    adapter_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "source_model": "melix-test-text",
                "adapter_set_hash": "adapter-legacy",
                "adapter_name": "legacy-adapter",
                "weights_path": str(adapter_weights_path),
                "training_mode": "qlora",
                "quantization_mode": "quantized_base",
                "target_modules": " model.layers.0.self_attn.q_proj, model.layers.0.mlp.gate_proj ",
            }
        ) + "\n",
        encoding="utf-8",
    )

    result = AdapterActivationPipeline().run(
        job_id="activate-legacy",
        request_ext={
            "artifact_path": str(adapter_manifest_path),
            "activation_mode": "adapter_backed_runtime",
        },
        source_model=_text_model(
            model_path=str(tmp_path / "base-model"),
            quant_profile_id="q4",
        ),
        output_dir=tmp_path / "activate",
    )

    assert result.manifest["quantized_target_module_guard"] == "accepted"


def test_adapter_runtime_plan_reuses_base_and_isolates_adapters(tmp_path: Path) -> None:
    source_model = _text_model(model_path=str(tmp_path / "base-model"), quant_profile_id="q4")
    adapter_scope = {
        "adapter_scope": "model",
        "training_surface": "model",
        "component_model_type": "",
        "component_family": "gemma",
        "component_model_path": str(tmp_path / "base-model"),
    }
    first = build_adapter_runtime_manifest_fields(
        source_model=source_model,
        adapter_manifest={
            "adapter_name": "alpha",
            "adapter_set_hash": "adapter-alpha",
            "job_id": "train-alpha",
        },
        adapter_manifest_path=tmp_path / "alpha.adapter.json",
        adapter_weights_path=str(tmp_path / "alpha" / "adapters.safetensors"),
        activation_mode="adapter_backed_runtime",
        adapter_scope=adapter_scope,
    )
    second = build_adapter_runtime_manifest_fields(
        source_model=source_model,
        adapter_manifest={
            "adapter_name": "beta",
            "adapter_set_hash": "adapter-beta",
            "job_id": "train-beta",
        },
        adapter_manifest_path=tmp_path / "beta.adapter.json",
        adapter_weights_path=str(tmp_path / "beta" / "adapters.safetensors"),
        activation_mode="adapter_backed_runtime",
        adapter_scope=adapter_scope,
    )

    assert first["adapter_runtime.base_reuse_key"] == second["adapter_runtime.base_reuse_key"]
    assert first["adapter_runtime.adapter_isolation_key"] != second["adapter_runtime.adapter_isolation_key"]
    assert first["adapter_runtime.switch_mode"] == "base_reuse_adapter_swap"
    assert second["adapter_runtime.sharing_policy"] == "shared_base_isolated_adapter"


def test_adapter_runtime_plan_marks_fused_activation_as_full_model_load(tmp_path: Path) -> None:
    source_model = _text_model(model_path=str(tmp_path / "base-model"), quant_profile_id="q4")
    adapter_scope = {
        "adapter_scope": "model",
        "training_surface": "model",
        "component_model_type": "",
        "component_family": "gemma",
        "component_model_path": str(tmp_path / "base-model"),
    }

    runtime_fields = build_adapter_runtime_manifest_fields(
        source_model=source_model,
        adapter_manifest={
            "adapter_name": "alpha",
            "adapter_set_hash": "adapter-alpha",
            "job_id": "train-alpha",
        },
        adapter_manifest_path=tmp_path / "alpha.adapter.json",
        adapter_weights_path=str(tmp_path / "alpha" / "adapters.safetensors"),
        activation_mode="fused_derived_model",
        adapter_scope=adapter_scope,
    )

    assert runtime_fields["adapter_runtime.switch_mode"] == "full_model_load"
    assert runtime_fields["adapter_runtime.sharing_policy"] == "isolated_fused_model"
    assert runtime_fields["adapter_runtime.compatibility_status"] == "not_applicable"
    assert len(runtime_fields["adapter_runtime.base_reuse_key"]) == 64
    assert len(runtime_fields["adapter_runtime.adapter_isolation_key"]) == 64
