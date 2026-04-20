"""Phase 3B chunked-training evidence harness (milestone #43).

Reuses Phase 3A's fixtures and env-gating shape. When enabled, runs a real
LoRA training pass with ``chunked_training=true`` and ``chunk_size=2048``
against each fixture, writes ``chunked_evidence.json`` next to the fixture,
and ASSERTS the Phase 3 quantitative gate against the committed
``baseline_evidence.json``:

    chunked.tokens_per_second >= baseline.tokens_per_second * 1.25
    OR
    chunked.peak_memory_gb    <= baseline.peak_memory_gb    * 0.70

Unlike Phase 3A (which was the ruler), this test is pass/fail on the gate.
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
_CHUNK_SIZE = 2048
_TOKENS_PER_SECOND_GATE = 1.25  # ≥25% improvement
_PEAK_MEMORY_GATE = 0.70  # ≥30% reduction


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


def _load_committed_baseline(fixture_dir: Path) -> dict:
    baseline_path = fixture_dir / "baseline_evidence.json"
    if not baseline_path.is_file():
        pytest.fail(
            f"Baseline evidence missing at {baseline_path}. Run the Phase 3A "
            "harness first."
        )
    return json.loads(baseline_path.read_text(encoding="utf-8"))


def _build_training_config(
    *,
    model_path: Path,
    sample_count: int,
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
                "max_seq_length": str(_CHUNK_SIZE),
                "chunked_training": "true",
                "chunk_size": str(_CHUNK_SIZE),
                "response_only": "true",
                "num_layers": "1",
                "rank": "8",
                "alpha": "16",
                "learning_rate": "1e-4",
                "adapter_name": "phase3-chunked",
            },
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=sample_count,
        )
    except ModelOperationError as exc:  # pragma: no cover - surfaced by pytest
        pytest.fail(f"normalize_training_config rejected Phase 3B chunked config: {exc}")


def _evidence_path(fixture_dir: Path) -> Path:
    return fixture_dir / "chunked_evidence.json"


def _mlx_lm_version() -> str:
    try:
        return importlib.metadata.version("mlx-lm")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - dev only
        return "unknown"


def _assert_gate_passed(
    *,
    fixture_id: str,
    baseline_metrics: dict,
    chunked_metrics: dict,
) -> tuple[float, float]:
    """Return (throughput_ratio, memory_ratio) and assert at least one gate met."""

    baseline_tps = float(baseline_metrics.get("tokens_per_second", 0.0))
    baseline_peak = float(baseline_metrics.get("peak_memory_gb", 0.0))
    chunked_tps = float(chunked_metrics.get("tokens_per_second", 0.0))
    chunked_peak = float(chunked_metrics.get("peak_memory_gb", 0.0))

    throughput_ratio = chunked_tps / baseline_tps if baseline_tps > 0.0 else 0.0
    memory_ratio = chunked_peak / baseline_peak if baseline_peak > 0.0 else float("inf")

    throughput_passed = throughput_ratio >= _TOKENS_PER_SECOND_GATE
    memory_passed = memory_ratio <= _PEAK_MEMORY_GATE

    assert throughput_passed or memory_passed, (
        f"Phase 3 gate FAILED for {fixture_id}: "
        f"tokens/sec {chunked_tps:.3f} vs baseline {baseline_tps:.3f} "
        f"(ratio {throughput_ratio:.2f}, need ≥{_TOKENS_PER_SECOND_GATE:.2f}); "
        f"peak {chunked_peak:.2f} GB vs baseline {baseline_peak:.2f} GB "
        f"(ratio {memory_ratio:.2f}, need ≤{_PEAK_MEMORY_GATE:.2f})."
    )

    return throughput_ratio, memory_ratio


def _run_chunked(
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

    baseline_evidence = _load_committed_baseline(fixture_dir)
    baseline_metrics = baseline_evidence["training_metrics"]

    normalized_dir = tmp_root / "normalized"
    adapter_dir = tmp_root / "adapter"
    _write_normalized_dataset(fixture_dir, normalized_dir)

    config = _build_training_config(
        model_path=model_path,
        sample_count=len(samples),
    )

    request = TrainingRequest(
        job_id=f"phase3-chunked-{manifest['dataset_id']}",
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

    assert result.metrics.tokens_seen > 0, "chunked run must see at least one token"
    assert result.metrics.examples_seen > 0, "chunked run must see at least one example"
    assert result.weights_path.is_file(), "chunked run must produce an adapter safetensors"

    # Chunking-specific invariants: proving the chunker actually ran and that
    # every emitted chunk was probed by the Phase 2 response-only-boundary
    # pass (so cross-chunk masking is correct).
    assert result.metrics.chunked_enabled is True
    assert result.metrics.source_sample_count == len(samples)
    assert result.metrics.chunk_count > len(samples), (
        f"chunk_count {result.metrics.chunk_count} must exceed source "
        f"sample_count {len(samples)} — otherwise no chunking happened."
    )
    assert result.metrics.response_only_boundary_sample_count == result.metrics.chunk_count, (
        "response-only boundary must be computed for every emitted chunk."
    )

    metrics_dict = asdict(result.metrics)
    for ephemeral_key in ("latest_checkpoint_path", "resume_source_path"):
        metrics_dict[ephemeral_key] = ""

    throughput_ratio, memory_ratio = _assert_gate_passed(
        fixture_id=manifest["dataset_id"],
        baseline_metrics=baseline_metrics,
        chunked_metrics=metrics_dict,
    )

    evidence = {
        "schema_version": "melix.lora_long_context_chunked.v1",
        "fixture_id": manifest["dataset_id"],
        "sample_count": len(samples),
        "chunk_count": result.metrics.chunk_count,
        "chunk_size": _CHUNK_SIZE,
        "target_tokens_per_sample": target_tokens,
        "template_family": manifest.get("template_family", "qwen"),
        "model_id": _MODEL_ID,
        "mlx_lm_version": _mlx_lm_version(),
        "generated_at_unix_ms": int(time.time() * 1000),
        "harness_duration_ms": round(duration_ms_monotonic, 2),
        "source_baseline_reference": "baseline_evidence.json",
        "gate_tokens_per_second_ratio": round(throughput_ratio, 4),
        "gate_peak_memory_ratio": round(memory_ratio, 4),
        "gate_tokens_per_second_threshold": _TOKENS_PER_SECOND_GATE,
        "gate_peak_memory_threshold": _PEAK_MEMORY_GATE,
        "training_metrics": metrics_dict,
    }
    _evidence_path(fixture_dir).write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_phase3_long_context_chunked_4k(tmp_path: Path) -> None:
    model_path = _require_evidence_gates()
    _run_chunked(_4K_FIXTURE, target_tokens=4000, model_path=model_path, tmp_root=tmp_path)


def test_phase3_long_context_chunked_8k(tmp_path: Path) -> None:
    model_path = _require_evidence_gates()
    if os.environ.get(_EIGHT_K_ENV, "").strip() != "1":
        pytest.skip(
            f"{_EIGHT_K_ENV}=1 not set. The 8k fixture needs ≥20 GB unified "
            "memory — gated behind its own opt-in."
        )
    _run_chunked(_8K_FIXTURE, target_tokens=8000, model_path=model_path, tmp_root=tmp_path)
