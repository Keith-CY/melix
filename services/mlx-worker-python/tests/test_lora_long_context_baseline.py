"""Phase 3A baseline-evidence harness for long-context LoRA training.

Gated by ``MELIX_PHASE3_LONG_CONTEXT_EVIDENCE=1`` AND
``MELIX_PHASE8_REAL_SMALL_MODEL_PATH`` so it skips cleanly in default CI.

When enabled, it runs a real tiny LoRA training pass against each
long-context fixture on the cached Qwen3.5-0.8B-OptiQ-4bit model and writes
``baseline_evidence.json`` next to the fixture. Those evidence files become
the numbers Phase 3B's chunked-training implementation must beat by
≥25% tokens/sec OR ≥30% peak memory reduction (milestone #43 Phase 3 gate).

This slice deliberately does NOT assert the improvement gate — it is the
measurement ruler, not the ruling.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import time
from dataclasses import asdict
from pathlib import Path

import pytest

from packages.protocol.python.worker.v1 import common_pb2
from worker.model_ops import training_config as training_config_module
from worker.model_ops.errors import ModelOperationError
from worker.model_ops.mlx_lm_runner import MLXLMRunner, TrainingRequest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE_ROOT = (
    _REPO_ROOT / "services" / "mlx-worker-python" / "fixtures" / "training"
)
_4K_FIXTURE = _FIXTURE_ROOT / "long-context-4k.v1"
_8K_FIXTURE = _FIXTURE_ROOT / "long-context-8k.v1"
_EVIDENCE_ENV = "MELIX_PHASE3_LONG_CONTEXT_EVIDENCE"
_MODEL_PATH_ENV = "MELIX_PHASE8_REAL_SMALL_MODEL_PATH"
_EIGHT_K_ENV = "MELIX_PHASE3_LONG_CONTEXT_8K"
_MODEL_ID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"


def _require_evidence_gates() -> Path:
    if os.environ.get(_EVIDENCE_ENV, "").strip() != "1":
        pytest.skip(
            f"{_EVIDENCE_ENV}=1 not set. This harness only runs when the "
            "maintainer explicitly opts in — it executes real LoRA training."
        )
    model_path = os.environ.get(_MODEL_PATH_ENV, "").strip()
    if not model_path:
        pytest.skip(
            f"{_MODEL_PATH_ENV} must point at the cached "
            "mlx-community/Qwen3.5-0.8B-OptiQ-4bit snapshot."
        )
    resolved = Path(model_path).expanduser().resolve()
    if not resolved.is_dir():
        pytest.skip(f"Model path {resolved} does not exist.")
    return resolved


def _load_fixture_samples(fixture_dir: Path) -> list[dict]:
    samples_path = fixture_dir / "samples.jsonl"
    if not samples_path.is_file():
        pytest.fail(f"Fixture samples.jsonl missing at {samples_path}")
    return [
        json.loads(line)
        for line in samples_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _load_fixture_manifest(fixture_dir: Path) -> dict:
    return json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))


def _write_normalized_dataset(fixture_dir: Path, normalized_dir: Path) -> None:
    normalized_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fixture_dir / "samples.jsonl", normalized_dir / "train.jsonl")
    # MLX-LM's load_local_dataset tolerates missing valid.jsonl — it returns []
    # for the subset. We leave valid.jsonl absent so training doesn't try
    # eval against a non-existent set.


def _build_training_config(
    *,
    model_path: Path,
    sample_count: int,
    max_seq_length: int,
) -> training_config_module.LoRATrainingConfig:
    source_model = common_pb2.ModelSpec(
        model_id=_MODEL_ID,
        model_path=str(model_path),
        model_kind="text",
        quant_profile_id="q4",
    )
    try:
        return training_config_module.normalize_training_config(
            source_model=source_model,
            ext={
                "training_mode": "qlora",
                "batch_size": "1",
                "epochs": "1",
                "max_steps": "5",
                "max_seq_length": str(max_seq_length),
                "response_only": "true",
                "num_layers": "1",
                "rank": "8",
                "alpha": "16",
                "learning_rate": "1e-4",
                "adapter_name": "phase3-baseline",
            },
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=sample_count,
        )
    except ModelOperationError as exc:  # pragma: no cover - surfaced by pytest
        pytest.fail(f"normalize_training_config rejected Phase 3 baseline config: {exc}")


def _evidence_path(fixture_dir: Path) -> Path:
    return fixture_dir / "baseline_evidence.json"


def _mlx_lm_version() -> str:
    try:
        return importlib.metadata.version("mlx-lm")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - dev only
        return "unknown"


def _run_baseline(
    fixture_dir: Path,
    *,
    target_tokens: int,
    model_path: Path,
    tmp_root: Path,
) -> None:
    samples = _load_fixture_samples(fixture_dir)
    manifest = _load_fixture_manifest(fixture_dir)
    assert manifest.get("target_tokens_per_sample") == target_tokens
    assert manifest.get("format") == "chat_messages"
    assert manifest.get("sample_count") == len(samples)

    normalized_dir = tmp_root / "normalized"
    adapter_dir = tmp_root / "adapter"
    _write_normalized_dataset(fixture_dir, normalized_dir)

    config = _build_training_config(
        model_path=model_path,
        sample_count=len(samples),
        max_seq_length=max(target_tokens + 256, 4096),
    )

    request = TrainingRequest(
        job_id=f"phase3-baseline-{manifest['dataset_id']}",
        base_model_id=_MODEL_ID,
        model_path=model_path,
        model_revision="main",
        adapter_output_dir=adapter_dir,
        normalized_dataset_dir=normalized_dir,
        config=config,
        dataset_format="chat_messages",
    )

    started_at = time.time()
    result = MLXLMRunner().train_native(request)
    duration_ms_monotonic = (time.time() - started_at) * 1000.0

    assert result.metrics.tokens_seen > 0, "baseline must see at least one token"
    assert result.metrics.examples_seen > 0, "baseline must see at least one example"
    assert result.weights_path.is_file(), "baseline must produce an adapter safetensors"

    # Drop machine-specific tmp paths so the committed evidence diffs cleanly
    # across maintainers and Phase 3B comparison runs. The checkpoint/resume
    # paths are ephemeral pytest tmp dirs; they have no value post-run.
    metrics_dict = asdict(result.metrics)
    for ephemeral_key in ("latest_checkpoint_path", "resume_source_path"):
        metrics_dict[ephemeral_key] = ""

    evidence = {
        "schema_version": "melix.lora_long_context_baseline.v1",
        "fixture_id": manifest["dataset_id"],
        "sample_count": len(samples),
        "target_tokens_per_sample": target_tokens,
        "template_family": manifest.get("template_family", "qwen"),
        "model_id": _MODEL_ID,
        "mlx_lm_version": _mlx_lm_version(),
        "generated_at_unix_ms": int(time.time() * 1000),
        "harness_duration_ms": round(duration_ms_monotonic, 2),
        "training_metrics": metrics_dict,
    }
    _evidence_path(fixture_dir).write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_phase3_long_context_baseline_4k(tmp_path: Path) -> None:
    model_path = _require_evidence_gates()
    _run_baseline(_4K_FIXTURE, target_tokens=4000, model_path=model_path, tmp_root=tmp_path)


def test_phase3_long_context_baseline_8k(tmp_path: Path) -> None:
    model_path = _require_evidence_gates()
    if os.environ.get(_EIGHT_K_ENV, "").strip() != "1":
        pytest.skip(
            f"{_EIGHT_K_ENV}=1 not set. The 8k fixture needs ≥20 GB unified "
            "memory — gated behind its own opt-in."
        )
    _run_baseline(_8K_FIXTURE, target_tokens=8000, model_path=model_path, tmp_root=tmp_path)
