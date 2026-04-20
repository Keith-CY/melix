"""Env-gated integration harness for adapter-backed runtime (issue #12 · Module 1).

Trains a tiny LoRA adapter against a 2-sample fixture, activates adapter-backed,
and exercises the real ``AutoMLXBackend.load_model`` + ``generate_tokens`` path
to prove the serving chain works end-to-end — not just the metadata surface.

Gates:
  - ``MELIX_PHASE8_REAL_SMALL_MODEL_E2E=1``
  - ``MELIX_PHASE8_REAL_SMALL_MODEL_PATH=<cached Qwen3.5-0.8B-OptiQ-4bit snapshot>``

Skips cleanly without the opt-in — CI never runs this harness. The adapter
training takes <30 s on 64 GB Apple Silicon; total wall time ~40-60 s.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from packages.protocol.python.worker.v1 import common_pb2
from worker.model_ops import training_config as training_config_module
from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.errors import ModelOperationError
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline
from worker.model_ops.mlx_lm_runner import MLXLMRunner, TrainingRequest
from worker.runtime.mlx_text_runtime import AutoMLXBackend


_E2E_ENV = "MELIX_PHASE8_REAL_SMALL_MODEL_E2E"
_MODEL_PATH_ENV = "MELIX_PHASE8_REAL_SMALL_MODEL_PATH"
_MODEL_ID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DATASET_FIXTURE = (
    _REPO_ROOT
    / "services"
    / "mlx-worker-python"
    / "fixtures"
    / "training"
    / "melix-dev-dataset.v1"
)


def _require_gates() -> Path:
    if os.environ.get(_E2E_ENV, "").strip() != "1":
        pytest.skip(
            f"{_E2E_ENV}=1 not set. This harness runs real LoRA training + "
            "real inference against the cached Qwen snapshot."
        )
    model_path = os.environ.get(_MODEL_PATH_ENV, "").strip()
    if not model_path:
        pytest.skip(
            f"{_MODEL_PATH_ENV} must point at a cached "
            "mlx-community/Qwen3.5-0.8B-OptiQ-4bit snapshot."
        )
    resolved = Path(model_path).expanduser().resolve()
    if not resolved.is_dir():
        pytest.skip(f"Model path {resolved} does not exist.")
    return resolved


def _build_source_model(model_path: Path) -> common_pb2.ModelSpec:
    source = common_pb2.ModelSpec(
        model_id=_MODEL_ID,
        model_path=str(model_path),
        model_kind="text",
        quant_profile_id="q4",
    )
    # Qwen dense models resolve as llama-family at the runtime adapter layer
    # (GQA + standard RoPE). We set the LoRA family profile to qwen so the
    # training pipeline picks the right target modules, but we do NOT force
    # text_family_id — letting runtime auto-detection resolve the attention
    # + rope profile from the model config.
    source.ext["melix.lora.family_id"] = "qwen"
    source.ext["melix.lora.family_kind"] = "dense"
    source.ext["melix.lora.support_tier"] = "stable"
    source.ext["melix.lora.training_ready"] = "true"
    return source


def _train_adapter(
    *,
    source_model: common_pb2.ModelSpec,
    dataset_dir: Path,
    output_dir: Path,
) -> Path:
    """Return the path to the adapter package manifest."""
    samples_path = dataset_dir / "samples.jsonl"
    assert samples_path.is_file(), f"Missing dataset fixture at {samples_path}"

    # Materialize the normalized dataset dir MLX-LM expects (train.jsonl).
    normalized_dir = output_dir / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(samples_path, normalized_dir / "train.jsonl")

    config = training_config_module.normalize_training_config(
        source_model=source_model,
        ext={
            "training_mode": "qlora",
            "batch_size": "1",
            "epochs": "1",
            "max_steps": "2",
            "max_seq_length": "512",
            "response_only": "true",
            "num_layers": "1",
            "rank": "4",
            "alpha": "8",
            "learning_rate": "1e-4",
            "adapter_name": "module1-integration-adapter",
        },
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )

    adapter_output_dir = output_dir / "adapter"
    training_request = TrainingRequest(
        job_id="module1-integration-train",
        base_model_id=_MODEL_ID,
        model_path=Path(source_model.model_path),
        model_revision="main",
        adapter_output_dir=adapter_output_dir,
        normalized_dataset_dir=normalized_dir,
        config=config,
        dataset_format="chat_messages",
    )
    try:
        training_result = MLXLMRunner().train_native(training_request)
    except ModelOperationError as exc:  # pragma: no cover - surfaced by pytest
        pytest.fail(f"train_native failed: {exc}")

    # Write a minimal adapter-package manifest that matches what the Melix
    # LoRA training pipeline would emit. The activation pipeline only reads
    # a small subset of fields so the minimal manifest is sufficient.
    adapter_manifest_path = output_dir / "train_lora.adapter.json"
    adapter_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "job_id": "module1-integration-train",
                "source_model": source_model.model_id,
                "weights_path": str(training_result.weights_path),
                "adapter_name": "module1-integration-adapter",
                "adapter_set_hash": "module1integration0001",
                "desired_derived_model_alias": "Module1 Integration",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return adapter_manifest_path


def _activate_adapter_backed(
    *,
    source_model: common_pb2.ModelSpec,
    adapter_manifest_path: Path,
    output_dir: Path,
) -> dict:
    pipeline = AdapterActivationPipeline(runner=MLXLMRunner())
    result = pipeline.run(
        job_id="module1-integration-activate",
        request_ext={
            "artifact_path": str(adapter_manifest_path),
            "activation_mode": "adapter_backed_runtime",
        },
        source_model=source_model,
        output_dir=output_dir,
    )
    return result.manifest


def _build_derived_spec(source_model: common_pb2.ModelSpec, manifest: dict) -> common_pb2.ModelSpec:
    spec = common_pb2.ModelSpec(
        model_id=manifest["derived_model_id"],
        model_path=manifest["source_model_path"],
        model_kind="text",
        quant_profile_id=source_model.quant_profile_id,
    )
    # Propagate the typed RuntimeMode enum authoritatively.
    spec.runtime_mode = common_pb2.RUNTIME_MODE_ADAPTER_BACKED
    spec.ext.update(source_model.ext)
    spec.ext["melix.activation_mode"] = manifest["activation_mode"]
    spec.ext["melix.adapter_manifest_path"] = manifest["adapter_manifest_path"]
    spec.ext["melix.adapter_weights_path"] = manifest["adapter_weights_path"]
    spec.ext["melix.adapter_set_hash"] = manifest["adapter_set_hash"]
    spec.ext["melix.derived_from_model_id"] = source_model.model_id
    return spec


def test_adapter_backed_runtime_end_to_end(tmp_path: Path) -> None:
    model_path = _require_gates()

    # Slice 1.2 proves the full chain works: train → activate adapter-backed
    # → load through AutoMLXBackend → generate tokens. Failures at any stage
    # surface here rather than only in the heavyweight Phase 8 acceptance
    # bundle flow.
    source_model = _build_source_model(model_path)
    adapter_manifest_path = _train_adapter(
        source_model=source_model,
        dataset_dir=_DATASET_FIXTURE,
        output_dir=tmp_path / "train",
    )
    manifest = _activate_adapter_backed(
        source_model=source_model,
        adapter_manifest_path=adapter_manifest_path,
        output_dir=tmp_path / "activate",
    )

    assert manifest["activation_mode"] == "adapter_backed_runtime"
    assert manifest["runtime_mode"] == int(common_pb2.RUNTIME_MODE_ADAPTER_BACKED)

    derived_spec = _build_derived_spec(source_model, manifest)
    backend = AutoMLXBackend()
    loaded = backend.load_model(derived_spec)

    # Contract: the adapter_dir metadata is populated from the manifest path
    # so downstream callers (control plane summary, CLI show detail, etc.)
    # can inspect which adapter was applied.
    assert loaded["activation_mode"] == "adapter_backed_runtime"
    assert loaded["adapter_weights_path"].endswith("adapters.safetensors")
    assert Path(loaded["adapter_dir"]).is_dir(), (
        f"Adapter dir {loaded['adapter_dir']} must exist post-training."
    )

    # End-to-end proof: generate at least one token via the adapter-backed
    # path. Sampling config is deterministic (temp=0) + low max_tokens to
    # keep wall time minimal. Any completion output demonstrates the base
    # model + adapter loaded and inference ran without error.
    sampling = common_pb2.SamplingConfig(
        temperature=0.0,
        top_p=1.0,
        top_k=1,
        max_output_tokens=4,
    )

    class _NoCancel:
        def is_set(self) -> bool:
            return False

    prompt = "Reply with DERIVED_OK."
    events = list(backend.generate_tokens(loaded, prompt, sampling, _NoCancel()))
    assert events, "generate_tokens must yield at least one event through adapter-backed runtime"
    # At least one event carries non-empty text OR a finish reason — the
    # stream_generate contract.
    produced_text = "".join(ev.text for ev in events)
    assert produced_text or any(ev.finish_reason for ev in events), (
        "adapter-backed runtime produced no text and no finish reason"
    )
