from __future__ import annotations

import json
from pathlib import Path
import sys
import types

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.deterministic_lora_runner import DeterministicLoRARunner
from worker.model_ops.errors import ModelOperationError
from worker.model_ops import training_config as training_config_module
from worker.model_ops import lora_runtime_metadata as lora_runtime_metadata_module
from worker.model_ops.lora_runtime_metadata import build_lora_canary_receipt_fields
from worker.model_ops.lora_training_pipeline import (
    LoRATrainingPipeline,
)
from worker.model_ops.training_runtime_preflight import (
    training_runtime_preflight_fields as _training_runtime_preflight_fields,
)
from worker.model_ops.mlx_lm_runner import TrainingMetrics


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


def test_training_admission_rejects_invalid_hyperparameters_with_typed_details() -> None:
    with pytest.raises(ModelOperationError) as exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(family_id="qwen"),
            ext={"rank": "0"},
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )

    assert exc.value.code == "invalid_argument"
    assert exc.value.details == {
        "field": "rank",
        "reason": "below_minimum",
        "received": "0",
        "minimum": "1",
        "allowed_bounds": ">=1",
        "http_status": "422",
    }


def test_training_admission_receipt_records_resolved_controls(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-with-validation",
        valid_lines=[
            json.dumps(
                {
                    "messages": [
                        {"role": "user", "content": "validate"},
                        {"role": "assistant", "content": "ok"},
                    ]
                }
            )
        ],
    )

    result = LoRATrainingPipeline(runner=DeterministicLoRARunner()).run(
        job_id="train-admission-receipts",
        request_ext={
            "operation": "train_lora",
            "adapter_name": "receipt-adapter",
            "dataset_uri": str(dataset_dir),
            "max_steps": "0",
            "grad_clip": "0.25",
        },
        source_model=_text_model(family_id="qwen"),
        output_dir=tmp_path / "output",
        jobs_root=tmp_path / "jobs",
    )

    manifest = result.manifest
    assert manifest["validation_errors"] == []
    assert manifest["resolved_bounds"]["max_steps"] == {
        "received": "0",
        "resolved": 0,
        "sentinel": "no_explicit_cap",
        "allowed_bounds": "0 or >=1",
    }
    assert manifest["capability_gate"]["adapter_family"] == "lora"
    assert manifest["capability_gate"]["response_only_supported"] is True
    assert manifest["dataset_files_resolved"] == {
        "source_manifest_path": str(dataset_dir.resolve() / "manifest.json"),
        "source_samples_path": str(dataset_dir.resolve() / "samples.jsonl"),
        "source_valid_path": str(dataset_dir.resolve() / "valid.jsonl"),
        "normalized_manifest_path": str(tmp_path / "output" / "normalized_dataset" / "manifest.json"),
        "normalized_train_path": str(tmp_path / "output" / "normalized_dataset" / "train.jsonl"),
        "normalized_valid_path": str(tmp_path / "output" / "normalized_dataset" / "valid.jsonl"),
    }
    assert manifest["grad_clip_policy"] == {
        "requested": "0.25",
        "resolved": 0.25,
        "enabled": True,
        "source": "request",
    }
    assert manifest["eval_batch_size"] == {
        "requested": "",
        "resolved": 1,
        "source": "default",
        "validation_sample_count": 1,
    }
    assert manifest["scheduler_kwargs_omitted"] == {
        "omitted": True,
        "reason": "scheduler_not_configured",
        "keys": [],
    }


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


def test_training_runtime_preflight_classifies_dependency_limited_inspection_without_runtime_imports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    imported: list[str] = []

    def fake_find_spec(name: str):
        if name in {"mlx", "mlx_lm"}:
            return None
        if name == "PIL":
            return object()
        return object()

    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("importlib.util.find_spec", fake_find_spec)

    def fake_import_module(name: str):
        imported.append(name)
        raise RuntimeError("Pillow binary mismatch")

    monkeypatch.setattr("importlib.import_module", fake_import_module)

    fields = _training_runtime_preflight_fields(
        source_model=_gemma4_vlm_model(model_path=str(tmp_path / "vlm")),
        adapter_scope={"training_surface": "text_backbone"},
        inspection_only=True,
    )

    assert fields["runtime_gate"] == "unsupported"
    assert fields["inspection_only_import"] is True
    assert fields["native_load_status"] == "disabled"
    assert fields["fallback_reader"] == "metadata_only"
    assert fields["unsupported_reason"] == "non_apple_host"
    assert fields["media_decoder_dependency"]["state"] == "broken"
    assert fields["media_decoder_dependency"]["module"] == "PIL"
    assert fields["disabled_decoder_paths"] == ["media"]
    assert imported == ["PIL"]


def test_text_only_lora_manifest_records_broken_optional_decoder_without_blocking(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_find_spec(name: str):
        if name == "PIL":
            return object()
        return object()

    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("importlib.util.find_spec", fake_find_spec)
    monkeypatch.setattr(
        "importlib.import_module",
        lambda name: (_ for _ in ()).throw(RuntimeError("Pillow binary mismatch")),
    )
    dataset_dir = _write_dataset_package(tmp_path / "dataset")

    result = LoRATrainingPipeline(runner=DeterministicLoRARunner()).run(
        job_id="train-text-broken-decoder",
        request_ext={
            "operation": "train_lora",
            "adapter_name": "text-adapter",
            "dataset_uri": str(dataset_dir),
        },
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        output_dir=tmp_path / "output",
        jobs_root=tmp_path / "jobs",
    )

    assert result.manifest["runtime_gate"] == "ready"
    assert result.manifest["inspection_only_import"] is False
    assert result.manifest["native_load_status"] == "available"
    assert result.manifest["media_decoder_dependency"]["state"] == "broken"
    assert result.manifest["disabled_decoder_paths"] == ["media"]
    assert result.manifest["fallback_reader"] == "none"
    assert result.manifest["unsupported_reason"] == ""
    assert result.manifest["traceback_cleanup_result"] == "not_applicable"
    assert result.manifest["retained_tensor_bytes_after_failure"] == 0


@pytest.mark.parametrize(
    ("decoder_specs", "expected_state", "expected_module", "expected_disabled_paths"),
    [
        ({"PIL": object()}, "healthy", "PIL", []),
        ({"PIL": None, "imageio": None, "av": None, "soundfile": None}, "missing", "", ["media"]),
    ],
)
def test_training_runtime_preflight_records_healthy_and_missing_decoder_states(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    decoder_specs: dict[str, object | None],
    expected_state: str,
    expected_module: str,
    expected_disabled_paths: list[str],
) -> None:
    def fake_find_spec(name: str):
        if name in {"mlx", "mlx_lm"}:
            return object()
        return decoder_specs.get(name, object())

    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("importlib.util.find_spec", fake_find_spec)
    monkeypatch.setattr("importlib.import_module", lambda name: object())

    fields = _training_runtime_preflight_fields(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        adapter_scope={"training_surface": "model"},
    )

    assert fields["runtime_gate"] == "ready"
    assert fields["media_decoder_dependency"]["state"] == expected_state
    assert fields["media_decoder_dependency"]["module"] == expected_module
    assert fields["disabled_decoder_paths"] == expected_disabled_paths


def test_training_runtime_preflight_reports_partial_decoder_state_when_video_decoder_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_find_spec(name: str):
        if name in {"mlx", "mlx_lm"}:
            return object()
        if name == "av":
            return None
        return object()

    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("importlib.util.find_spec", fake_find_spec)
    monkeypatch.setattr("importlib.import_module", lambda name: object())

    fields = _training_runtime_preflight_fields(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        adapter_scope={"training_surface": "model"},
    )

    dependency = fields["media_decoder_dependency"]
    assert dependency["state"] == "partial"
    assert dependency["module"] == "av"
    assert dependency["modules"]["PIL"]["state"] == "healthy"
    assert dependency["modules"]["av"]["state"] == "missing"
    assert fields["disabled_decoder_paths"] == ["media"]


def test_training_runtime_preflight_reports_broken_decoder_spec_lookup(
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

    fields = _training_runtime_preflight_fields(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        adapter_scope={"training_surface": "model"},
    )

    dependency = fields["media_decoder_dependency"]
    assert dependency["state"] == "broken"
    assert dependency["module"] == "PIL"
    assert dependency["modules"]["PIL"]["state"] == "broken"
    assert dependency["message"] == "corrupt decoder spec"
    assert fields["disabled_decoder_paths"] == ["media"]


def test_training_failure_cleanup_details_clear_nested_tracebacks_and_report_retained_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_mlx_pkg = types.ModuleType("mlx")
    fake_mlx_pkg.__path__ = []
    fake_mlx_core = types.ModuleType("mlx.core")
    fake_mlx_core.metal = types.SimpleNamespace(
        get_active_memory=lambda: 4096,
        get_peak_memory=lambda: 999999,
    )
    fake_mlx_pkg.core = fake_mlx_core
    monkeypatch.setitem(sys.modules, "mlx", fake_mlx_pkg)
    monkeypatch.setitem(sys.modules, "mlx.core", fake_mlx_core)

    captured: dict[str, BaseException] = {}

    class NestedFailureRunner(DeterministicLoRARunner):
        def train_native(self, request):  # noqa: ANN001
            _ = request
            try:
                try:
                    raise ValueError("inner tensor load failed")
                except ValueError as inner:
                    captured["inner"] = inner
                    raise RuntimeError("outer training failed") from inner
            except RuntimeError as outer:
                captured["outer"] = outer
                raise ModelOperationError(
                    code="backend_training_failure",
                    message="nested failure",
                ) from outer

    dataset_dir = _write_dataset_package(tmp_path / "dataset")

    with pytest.raises(ModelOperationError) as exc:
        LoRATrainingPipeline(runner=NestedFailureRunner()).run(
            job_id="train-nested-failure",
            request_ext={
                "operation": "train_lora",
                "adapter_name": "cleanup-adapter",
                "dataset_uri": str(dataset_dir),
            },
            source_model=_text_model(model_path=str(tmp_path / "base-model")),
            output_dir=tmp_path / "output",
            jobs_root=tmp_path / "jobs",
        )

    assert exc.value.code == "backend_training_failure"
    assert exc.value.details["traceback_cleanup_result"] == "cleared"
    assert exc.value.details["retained_tensor_bytes_after_failure"] == "4096"
    assert "outer training failed" in exc.value.details["traceback_summary_before_cleanup"]
    assert "inner tensor load failed" in exc.value.details["traceback_summary_before_cleanup"]
    assert captured["outer"].__traceback__ is None
    assert captured["inner"].__traceback__ is None


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


def test_lora_canary_aux_module_detection_uses_single_scandir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base_model_dir = tmp_path / "base-model"
    base_model_dir.mkdir()
    (base_model_dir / "tokenization_qwen2.py").write_text(
        "# custom tokenizer\n", encoding="utf-8"
    )
    (base_model_dir / "modeling_notes.txt").write_text("ignored\n", encoding="utf-8")

    def fail_glob(self: Path, pattern: str):
        raise AssertionError("auxiliary module detection should use os.scandir")  # pragma: no cover

    original_scandir = lora_runtime_metadata_module.os.scandir
    scanned_paths: list[str] = []

    def counting_scandir(path: str | Path):
        scanned_paths.append(str(path))
        return original_scandir(path)

    monkeypatch.setattr(Path, "glob", fail_glob)
    monkeypatch.setattr(lora_runtime_metadata_module.os, "scandir", counting_scandir)

    assert lora_runtime_metadata_module._aux_modules_restored(base_model_dir) is True
    assert scanned_paths == [str(base_model_dir)]


def test_lora_canary_aux_module_detection_returns_false_when_scandir_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base_model_dir = tmp_path / "base-model"

    def fail_scandir(path: str | Path):
        raise OSError("base model unavailable")

    monkeypatch.setattr(lora_runtime_metadata_module.os, "scandir", fail_scandir)

    assert lora_runtime_metadata_module._aux_modules_restored(base_model_dir) is False


def test_lora_quantized_kind_detection_uses_precompiled_patterns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_re_search(*_args: object, **_kwargs: object):
        raise AssertionError("quantized kind detection should reuse compiled patterns")  # pragma: no cover

    monkeypatch.setattr(lora_runtime_metadata_module.re, "search", fail_re_search)

    assert lora_runtime_metadata_module._quantized_kind_from_text("mlx q4 adapter") == "q4"
    assert lora_runtime_metadata_module._quantized_kind_from_text("not-a-q4suffix") == "unknown"


def test_lora_canary_receipt_detects_missing_checkpoint_resume_assets(
    tmp_path: Path,
) -> None:
    base_model_dir = tmp_path / "base-model"
    base_model_dir.mkdir()
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
    assert fields["tokenizer_config_path"] == ""
    assert fields["base_config_present"] is False
    assert fields["processor_resume_mode"] == "missing"
    assert fields["aux_modules_restored"] is False
    assert fields["merge_export_canary_result"] == (
        "fail:missing_base_config,missing_tokenizer_config,missing_auxiliary_modules"
    )
    assert fields["callback_api_drift_result"] == "fail:callback_arity_mismatch"

    missing_eos_base_dir = tmp_path / "base-model-missing-eos"
    missing_eos_base_dir.mkdir()
    (missing_eos_base_dir / "config.json").write_text('{"model_type":"qwen2"}\n', encoding="utf-8")
    (missing_eos_base_dir / "tokenizer_config.json").write_text(
        json.dumps({"tokenizer_class": "Qwen2Tokenizer"}) + "\n",
        encoding="utf-8",
    )
    missing_eos_adapter_dir = tmp_path / "adapter-missing-eos"
    missing_eos_adapter_dir.mkdir()
    missing_eos_adapter_config_path = missing_eos_adapter_dir / "adapter_config.json"
    missing_eos_adapter_config_path.write_text(
        json.dumps({"tokenizer_config": {"tokenizer_class": "Qwen2Tokenizer"}}) + "\n",
        encoding="utf-8",
    )
    missing_eos_weights_path = missing_eos_adapter_dir / "adapters.safetensors"
    missing_eos_weights_path.write_bytes(b"adapter")

    missing_eos_fields = build_lora_canary_receipt_fields(
        source_model=_text_model(model_path=str(missing_eos_base_dir)),
        adapter_output_dir=missing_eos_adapter_dir,
        adapter_config_path=missing_eos_adapter_config_path,
        weights_path=missing_eos_weights_path,
        training_metrics=TrainingMetrics(
            job_duration_ms=1.0,
            tokens_seen=8,
            examples_seen=1,
            loss_final=0.5,
            loss_best=0.5,
            learning_rate_final=1e-5,
        ),
    )

    assert missing_eos_fields["source_eos_token"] == ""
    assert missing_eos_fields["saved_eos_token"] == ""
    assert missing_eos_fields["merge_export_canary_result"] == (
        "fail:missing_source_eos_token,missing_saved_eos_token,missing_auxiliary_modules"
    )


def test_training_config_records_scheduler_kwargs_omission_receipt() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(),
        ext={"scheduler_kwargs_json": '{"warmup": 10}', "eval_batch_size": "3"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=4,
        validation_sample_count=2,
    )

    assert config.eval_batch_size == {
        "requested": "3",
        "resolved": 3,
        "source": "request",
        "validation_sample_count": 2,
    }
    assert config.scheduler_kwargs_omitted == {
        "omitted": True,
        "reason": "mlx_lm_lora_runner_does_not_accept_scheduler_kwargs",
        "keys": ["scheduler_kwargs_json"],
    }
