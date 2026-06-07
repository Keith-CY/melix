from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.engine.maintenance_core import MaintenanceCore
from worker.grpc_server import WorkerMaintenanceService
from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.deterministic_lora_runner import DeterministicLoRARunner
from worker.model_ops.errors import ModelOperationError
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline
from worker.model_ops.mlx_lm_runner import TrainingRequest, TrainingResult
from worker.model_ops import training_receipts as training_receipts_module
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry


class CountingRunner(DeterministicLoRARunner):
    def __init__(self) -> None:
        super().__init__()
        self.native_train_calls = 0

    def train_native(self, request: TrainingRequest) -> TrainingResult:
        self.native_train_calls += 1
        return super().train_native(request)


def _write_dataset_package(
    root: Path,
    *,
    format: str = "chat_messages",
    samples: list[dict],
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "melix-template-admission",
                "format": format,
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


def _build_service(tmp_path: Path, runner: DeterministicLoRARunner) -> WorkerMaintenanceService:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")
    service._core = MaintenanceCore(
        registry,
        jobs_root=tmp_path / "model-ops",
        lora_training_pipeline=LoRATrainingPipeline(runner=runner),
        adapter_activation_pipeline=AdapterActivationPipeline(runner=runner),
    )
    return service


def _prompt_completion_dataset(tmp_path: Path, name: str) -> Path:
    return _write_dataset_package(
        tmp_path / name,
        format="prompt_completion",
        samples=[{"prompt": "Say hi.", "completion": "Hi."}],
    )


def _chat_dataset(tmp_path: Path, name: str) -> Path:
    return _write_dataset_package(
        tmp_path / name,
        samples=[
            {
                "messages": [
                    {"role": "user", "content": "Say hi."},
                    {"role": "assistant", "content": "Hi."},
                ]
            }
        ],
    )


def test_train_lora_rejects_custom_template_missing_input_placeholder(tmp_path: Path) -> None:
    dataset_dir = _prompt_completion_dataset(tmp_path, "dataset-template-missing-input")
    service = _build_service(tmp_path, DeterministicLoRARunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-template-missing-input"),
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-template-adapter",
                    "dataset_uri": str(dataset_dir),
                    "custom_training_template": "Assistant: {OUTPUT}",
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_training_template"
    assert events[-1].failed.error.details["field"] == "custom_training_template"
    assert events[-1].failed.error.details["reason"] == "missing_required_placeholder"
    assert events[-1].failed.error.details["missing_placeholders"] == "{INPUT}"
    assert events[-1].failed.error.details["http_status"] == "422"


def test_train_lora_rejects_response_only_custom_template_missing_assistant_marker(
    tmp_path: Path,
) -> None:
    dataset_dir = _chat_dataset(tmp_path, "dataset-template-missing-marker")
    runner = CountingRunner()
    service = _build_service(tmp_path, runner)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-template-missing-marker"),
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-template-adapter",
                    "dataset_uri": str(dataset_dir),
                    "custom_training_template": "User: {INPUT}\nAssistant: {OUTPUT}",
                    "response_only": "true",
                },
            ),
            context=None,
        )
    )

    assert runner.native_train_calls == 0
    assert events[-1].failed.error.code == "invalid_training_template"
    assert events[-1].failed.error.details["field"] == "assistant_generation_marker"
    assert events[-1].failed.error.details["reason"] == "missing_assistant_generation_marker"
    assert (
        events[-1].failed.error.details["required_markers"]
        == "<|assistant|>,<|assistant_start|>,<|start_header_id|>assistant<|end_header_id|>"
    )
    assert events[-1].failed.error.details["http_status"] == "422"


def test_train_lora_rejects_two_example_custom_template_without_separator(
    tmp_path: Path,
) -> None:
    dataset_dir = _prompt_completion_dataset(tmp_path, "dataset-template-two-example")
    service = _build_service(tmp_path, DeterministicLoRARunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-template-two-example"),
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-template-adapter",
                    "dataset_uri": str(dataset_dir),
                    "custom_training_template": (
                        "Example 1 {INPUT} <|assistant|>{OUTPUT}\n"
                        "Example 2 {INPUT} <|assistant|>{OUTPUT}"
                    ),
                    "assistant_generation_marker": "<|assistant|>",
                    "template_example_count": "2",
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_training_template"
    assert events[-1].failed.error.details["field"] == "template_example_separator"
    assert events[-1].failed.error.details["reason"] == "missing_two_example_separator"
    assert events[-1].failed.error.details["required_placeholders"] == "{INPUT},{OUTPUT}"
    assert events[-1].failed.error.details["http_status"] == "422"


def test_train_lora_records_accepted_custom_template_receipt(tmp_path: Path) -> None:
    dataset_dir = _prompt_completion_dataset(tmp_path, "dataset-template-accepted")
    runner = CountingRunner()
    service = _build_service(tmp_path, runner)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-template-accepted"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-template-adapter",
                    "dataset_uri": str(dataset_dir),
                    "custom_training_template": "User: {INPUT}\n<|assistant|>{OUTPUT}",
                    "assistant_generation_marker": "<|assistant|>",
                },
            ),
            context=None,
        )
    )

    payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)
    assert runner.native_train_calls == 1
    assert payload["training_template_receipt"] == {
        "template_source": "request",
        "template_path": "custom_training_template",
        "template_kind": "custom_prompt_completion",
        "required_placeholders": ["{INPUT}", "{OUTPUT}"],
        "assistant_marker_policy": {
            "required": False,
            "marker": "<|assistant|>",
            "source": "request",
        },
    }
    normalized_manifest = json.loads(
        Path(payload["normalized_dataset_manifest_path"]).read_text(encoding="utf-8")
    )
    assert normalized_manifest["training_template_receipt"] == payload["training_template_receipt"]


def test_training_template_receipt_accepts_custom_template_and_rejects_marker_drift() -> None:
    receipt = training_receipts_module.training_template_receipt(
        {
            "custom_training_template": "Prompt: {INPUT}\n<|assistant|>{OUTPUT}",
            "assistant_generation_marker": "<|assistant|>",
        },
        dataset_format="prompt_completion",
        response_only=False,
    )

    assert receipt == {
        "template_source": "request",
        "template_path": "custom_training_template",
        "template_kind": "custom_prompt_completion",
        "required_placeholders": ["{INPUT}", "{OUTPUT}"],
        "assistant_marker_policy": {
            "required": False,
            "marker": "<|assistant|>",
            "source": "request",
        },
    }

    with pytest.raises(ModelOperationError) as marker_error:
        training_receipts_module.training_template_receipt(
            {
                "custom_training_template": "Prompt: {INPUT}\nAssistant: {OUTPUT}",
                "assistant_generation_marker": "<|assistant|>",
            },
            dataset_format="prompt_completion",
            response_only=False,
        )

    assert marker_error.value.code == "invalid_training_template"
    assert marker_error.value.details["field"] == "assistant_generation_marker"
    assert marker_error.value.details["reason"] == "marker_not_found_in_template"
    assert marker_error.value.details["http_status"] == "422"


def test_training_template_receipt_accepts_inferred_marker_and_two_example_separator() -> None:
    assert training_receipts_module.training_template_receipt(
        {},
        dataset_format="chat_messages",
        response_only=False,
    ) == {
        "template_source": "builtin",
        "template_path": "",
        "template_kind": "chat_messages",
        "required_placeholders": [],
        "assistant_marker_policy": {
            "required": False,
            "marker": "",
            "source": "builtin",
        },
    }

    receipt = training_receipts_module.training_template_receipt(
        {
            "custom_training_template": (
                "Example 1\nPrompt: {INPUT}\n<|assistant_start|>{OUTPUT}"
                "\n{EXAMPLE_SEPARATOR}\n"
                "Example 2\nPrompt: {INPUT}\n<|assistant_start|>{OUTPUT}"
            ),
            "template_example_count": "2",
        },
        dataset_format="prompt_completion",
        response_only=True,
    )

    assert receipt["assistant_marker_policy"] == {
        "required": True,
        "marker": "<|assistant_start|>",
        "source": "template",
    }
