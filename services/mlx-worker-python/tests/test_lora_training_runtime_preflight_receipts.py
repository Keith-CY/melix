from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops import training_config as training_config_module
from worker.model_ops.deterministic_lora_runner import DeterministicLoRARunner
from worker.model_ops.errors import ModelOperationError
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline
from worker.model_ops.training_runtime_preflight import runtime_preflight_failure_details


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


def _text_model(*, model_path: str = "models/plain-llama", family_id: str = "") -> common_pb2.ModelSpec:
    model = common_pb2.ModelSpec(
        model_id="melix-test-text",
        model_path=model_path,
        model_kind="text",
        revision="main",
        max_context=4096,
    )
    if family_id:
        model.ext["text_family_id"] = family_id
    model.ext["text_layer_count"] = "2"
    return model


@pytest.mark.parametrize(
    ("received", "reason"),
    [
        ("nan", "not_finite"),
        ("-inf", "below_minimum"),
    ],
)
def test_training_admission_rejects_non_finite_float_hyperparameters(
    received: str,
    reason: str,
) -> None:
    with pytest.raises(ModelOperationError) as exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(family_id="qwen"),
            ext={"learning_rate": received},
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )

    assert exc.value.code == "invalid_argument"
    assert exc.value.details == {
        "field": "learning_rate",
        "reason": reason,
        "received": received,
        "minimum": "0.0",
        "allowed_bounds": "finite >=0.0",
        "http_status": "422",
    }


def test_training_failure_cleanup_preserves_runtime_preflight_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_find_spec(name: str):
        if name in {"mlx", "mlx_lm"}:
            return object()
        if name == "PIL":
            raise ValueError("corrupt decoder spec")
        return object()

    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("importlib.util.find_spec", fake_find_spec)

    class FailingRunner(DeterministicLoRARunner):
        def train_native(self, request):  # noqa: ANN001
            _ = request
            raise RuntimeError("native trainer crashed before adapter output")

    dataset_dir = _write_dataset_package(tmp_path / "dataset")

    with pytest.raises(ModelOperationError) as exc:
        LoRATrainingPipeline(runner=FailingRunner()).run(
            job_id="train-runtime-preflight-failure",
            request_ext={
                "operation": "train_lora",
                "adapter_name": "runtime-preflight-adapter",
                "dataset_uri": str(dataset_dir),
            },
            source_model=_text_model(model_path=str(tmp_path / "base-model")),
            output_dir=tmp_path / "output",
            jobs_root=tmp_path / "jobs",
        )

    assert exc.value.code == "backend_training_failure"
    assert exc.value.details["runtime_gate"] == "ready"
    assert exc.value.details["native_load_status"] == "available"
    assert exc.value.details["disabled_decoder_paths"] == "media"
    assert exc.value.details["media_decoder_dependency_state"] == "broken"
    assert exc.value.details["media_decoder_dependency_module"] == "PIL"
    assert exc.value.details["unsupported_reason"] == ""
    assert exc.value.details["traceback_cleanup_result"] == "cleared"
    retained_bytes = int(exc.value.details["retained_tensor_bytes_after_failure"])
    assert 0 <= retained_bytes < 1024 * 1024


def test_runtime_preflight_failure_details_coerces_unexpected_receipt_shapes() -> None:
    details = runtime_preflight_failure_details(
        {
            "runtime_gate": "unsupported",
            "inspection_only_import": True,
            "native_load_status": "disabled",
            "disabled_decoder_paths": "media",
            "fallback_reader": "metadata_only",
            "unsupported_reason": "non_apple_host",
            "media_decoder_dependency": "not-a-dict",
        }
    )

    assert details == {
        "runtime_gate": "unsupported",
        "inspection_only_import": "true",
        "native_load_status": "disabled",
        "disabled_decoder_paths": "media",
        "fallback_reader": "metadata_only",
        "unsupported_reason": "non_apple_host",
        "media_decoder_dependency_state": "",
        "media_decoder_dependency_module": "",
    }

    empty_paths_details = runtime_preflight_failure_details(
        {
            "runtime_gate": "ready",
            "disabled_decoder_paths": None,
        }
    )
    assert empty_paths_details["disabled_decoder_paths"] == ""
