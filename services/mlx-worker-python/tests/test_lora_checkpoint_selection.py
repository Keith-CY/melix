from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.deterministic_lora_runner import DeterministicLoRARunner
from worker.model_ops.lora_checkpoint_selection import (
    build_checkpoint_selection_receipt_fields,
    checkpoint_sort_key,
    checkpoint_step_from_path,
)
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline
from worker.model_ops.mlx_lm_runner import TrainingRequest, TrainingResult
from worker.productization.lora_experiment_store import LoraExperimentStore


def _text_model(model_path: Path) -> common_pb2.ModelSpec:
    return common_pb2.ModelSpec(
        model_id="melix-dev-text",
        model_path=str(model_path),
        model_kind="text",
        revision="dev",
        max_context=2048,
        ext={"text_family_id": "qwen", "text_layer_count": "2"},
    )


def _write_dataset_package(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "checkpoint-ordering",
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
                    {"role": "user", "content": "Rank checkpoints."},
                    {"role": "assistant", "content": "Use numeric step ordering."},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return root


class CheckpointOrderingRunner(DeterministicLoRARunner):
    def __init__(self) -> None:
        super().__init__()
        self.last_train_request: TrainingRequest | None = None
        self.last_activation_adapter_dir: Path | None = None

    def train_native(self, request: TrainingRequest) -> TrainingResult:
        self.last_train_request = request
        base = super().train_native(request)
        checkpoint_specs = (
            ("checkpoint-1", 0.51),
            ("checkpoint-9", 0.42),
            ("checkpoint-10", 0.39),
            ("checkpoint-100", 0.31),
            ("checkpoint-final", 0.88),
        )
        for checkpoint_name, _loss in checkpoint_specs:
            checkpoint_path = request.adapter_output_dir / checkpoint_name / "adapters.safetensors"
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            checkpoint_path.write_bytes(f"melix-test-{checkpoint_name}".encode("utf-8"))
        latest_checkpoint_path = request.adapter_output_dir / "checkpoint-100" / "adapters.safetensors"
        return replace(
            base,
            metrics=replace(
                base.metrics,
                checkpoint_count=len(checkpoint_specs),
                latest_checkpoint_path=str(latest_checkpoint_path),
                loss_best=0.31,
            ),
        )

    def activate_native(self, request):
        self.last_activation_adapter_dir = request.adapter_dir
        return super().activate_native(request)


def test_checkpoint_selection_receipt_fields_record_step_sort_key_and_loss_source() -> None:
    selected_path = "/tmp/model-ops-999/adapter/checkpoint-100/adapters.safetensors"
    fields = build_checkpoint_selection_receipt_fields(
        latest_checkpoint_path=selected_path,
        loss_best=0.31,
        loss_final=0.42,
    )

    assert fields == {
        "checkpoint_step": 100,
        "checkpoint_sort_key": "0000000100",
        "selected_checkpoint_path": selected_path,
        "selected_checkpoint_loss_source": "loss_best",
    }
    assert checkpoint_step_from_path(
        "/tmp/model-ops-999/adapter/checkpoint-final/adapters.safetensors"
    ) == -1
    assert checkpoint_step_from_path(
        "/tmp/model-ops-999/adapter/checkpoint-100-v2/adapters.safetensors"
    ) == 100
    assert checkpoint_step_from_path(
        "/tmp/model-ops-999/adapter/checkpoint-100-epoch-3/adapters.safetensors"
    ) == 100
    assert checkpoint_step_from_path("/tmp/model-ops-999/adapter-42.safetensors") == 42
    assert checkpoint_step_from_path("") == 0
    assert checkpoint_sort_key(
        checkpoint_step=-1,
        selected_checkpoint_path="/tmp/run/checkpoint-final/adapters.safetensors",
    ) == "no_numeric_step"
    assert build_checkpoint_selection_receipt_fields(
        latest_checkpoint_path="",
        loss_best=None,
        loss_final=0.42,
    ) == {
        "checkpoint_step": 0,
        "checkpoint_sort_key": "",
        "selected_checkpoint_path": "",
        "selected_checkpoint_loss_source": "",
    }
    assert build_checkpoint_selection_receipt_fields(
        latest_checkpoint_path=selected_path,
        loss_best=None,
        loss_final=0.42,
    )["selected_checkpoint_loss_source"] == "loss_final"
    assert build_checkpoint_selection_receipt_fields(
        latest_checkpoint_path=selected_path,
        loss_best=None,
        loss_final=None,
    )["selected_checkpoint_loss_source"] == ""


def test_lora_checkpoint_selection_receipts_drive_resume_and_activation_defaults(
    tmp_path: Path,
) -> None:
    base_model_dir = tmp_path / "base-model"
    base_model_dir.mkdir()
    (base_model_dir / "config.json").write_text('{"model_type":"qwen2"}\n', encoding="utf-8")
    (base_model_dir / "tokenizer_config.json").write_text(
        json.dumps({"eos_token": "<|endoftext|>"}) + "\n",
        encoding="utf-8",
    )
    dataset_dir = _write_dataset_package(tmp_path / "dataset")
    jobs_root = tmp_path / "jobs"
    runner = CheckpointOrderingRunner()
    source_model = _text_model(base_model_dir)

    result = LoRATrainingPipeline(runner=runner).run(
        job_id="model-ops-01529",
        request_ext={
            "operation": "train_lora",
            "adapter_name": "melix-checkpoint-ordering",
            "dataset_uri": str(dataset_dir),
            "experiment_group_id": "nightly-qwen35",
        },
        source_model=source_model,
        output_dir=jobs_root / "train_lora" / "model-ops-01529",
        jobs_root=jobs_root,
    )

    manifest = result.manifest
    assert manifest["checkpoint_count"] == 5
    assert manifest["checkpoint_step"] == 100
    assert manifest["checkpoint_sort_key"] == "0000000100"
    assert manifest["selected_checkpoint_path"].endswith(
        "checkpoint-100/adapters.safetensors"
    )
    assert manifest["selected_checkpoint_path"] == manifest["latest_checkpoint_path"]
    assert manifest["selected_checkpoint_loss_source"] == "loss_best"
    assert manifest["experiment.checkpoint_step"] == 100
    assert manifest["experiment.checkpoint_sort_key"] == "0000000100"
    assert manifest["experiment.selected_checkpoint_path"] == manifest[
        "selected_checkpoint_path"
    ]
    assert manifest["experiment.selected_checkpoint_loss_source"] == "loss_best"

    provenance_payload = json.loads(
        Path(manifest["adapter_provenance_manifest_path"]).read_text(encoding="utf-8")
    )
    provenance_adapter = provenance_payload["adapter"]
    assert provenance_adapter["checkpoint_step"] == 100
    assert provenance_adapter["checkpoint_sort_key"] == "0000000100"
    assert provenance_adapter["selected_checkpoint_path"] == manifest["selected_checkpoint_path"]
    assert provenance_adapter["selected_checkpoint_loss_source"] == "loss_best"

    index_payload = LoraExperimentStore().rebuild_index(jobs_root)
    group = index_payload["groups"][0]
    assert group["latest_checkpoint_step"] == 100
    assert group["latest_checkpoint_sort_key"] == "0000000100"
    assert group["latest_selected_checkpoint_path"] == manifest["selected_checkpoint_path"]
    assert group["best_known_adapter"]["selected_checkpoint_path"] == manifest[
        "selected_checkpoint_path"
    ]

    resumed = LoRATrainingPipeline(runner=runner).run(
        job_id="model-ops-01530",
        request_ext={
            "operation": "train_lora",
            "adapter_name": "melix-checkpoint-resume",
            "dataset_uri": str(dataset_dir),
            "resume_manifest_path": str(result.manifest_path),
        },
        source_model=source_model,
        output_dir=jobs_root / "train_lora" / "model-ops-01530",
        jobs_root=jobs_root,
    )
    assert runner.last_train_request is not None
    assert str(runner.last_train_request.resume_source_path) == manifest[
        "selected_checkpoint_path"
    ]
    assert resumed.manifest["resume_source_path"] == manifest["selected_checkpoint_path"]

    activation = AdapterActivationPipeline(runner=runner).run(
        job_id="activate-checkpoint-selection",
        request_ext={
            "artifact_path": str(result.manifest_path),
            "activation_mode": "fused_derived_model",
        },
        source_model=source_model,
        output_dir=tmp_path / "activate-output",
    )
    assert activation.manifest["adapter_weights_path"] == manifest["selected_checkpoint_path"]
    assert runner.last_activation_adapter_dir == Path(manifest["selected_checkpoint_path"]).parent
