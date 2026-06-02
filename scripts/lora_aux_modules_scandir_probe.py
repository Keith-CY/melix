#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(os.environ.get("MELIX_LORA_RUNTIME_METADATA_REPO_ROOT") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.model_ops import lora_runtime_metadata as metadata_module  # noqa: E402


_QUANTIZED_KIND_ORDER = ("4bit", "8bit", "q4", "q8", "optiq")


def _int_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name, "")
    return int(raw_value) if raw_value else default


def _seed_base_model(root: Path, *, noise_count: int, aux_index: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for index in range(noise_count):
        (root / f"noise-{index:05d}.txt").write_text("noise\n", encoding="utf-8")
    (root / f"tokenization_custom_{aux_index:05d}.py").write_text(
        "# auxiliary tokenizer module\n", encoding="utf-8"
    )


def _measure(*, noise_count: int, sample_count: int) -> dict[str, float]:
    elapsed_ms: list[float] = []
    peak_bytes: list[float] = []
    scandir_calls: list[float] = []

    with tempfile.TemporaryDirectory(prefix="melix-lora-aux-probe-") as temp_dir:
        base_model_dir = Path(temp_dir) / "base-model"
        _seed_base_model(base_model_dir, noise_count=noise_count, aux_index=noise_count)

        original_scandir = metadata_module.os.scandir
        for _ in range(sample_count):
            call_count = 0

            def counting_scandir(path: str | Path):
                nonlocal call_count
                call_count += 1
                return original_scandir(path)

            metadata_module.os.scandir = counting_scandir
            tracemalloc.start()
            started = time.perf_counter()
            try:
                restored = metadata_module._aux_modules_restored(base_model_dir)
            finally:
                elapsed = (time.perf_counter() - started) * 1000.0
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                metadata_module.os.scandir = original_scandir
            if not restored:
                raise RuntimeError("expected auxiliary module detection to return true")
            elapsed_ms.append(elapsed)
            peak_bytes.append(float(peak))
            scandir_calls.append(float(call_count))

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_ms),
        "elapsed_ms_min": min(elapsed_ms),
        "peak_bytes_mean": statistics.fmean(peak_bytes),
        "scandir_calls_mean": statistics.fmean(scandir_calls),
        "noise_file_count": float(noise_count),
        "sample_count": float(sample_count),
    }


def _baseline_processor_resume_mode(base_model_dir: Path) -> str:
    if (base_model_dir / "processor_config.json").is_file():
        return "processor_config"
    if (base_model_dir / "preprocessor_config.json").is_file():
        return "preprocessor_config"
    if (base_model_dir / "tokenizer_config.json").is_file():
        return "tokenizer_only"
    return "missing"


def _measure_processor_resume_mode(*, noise_count: int, sample_count: int) -> dict[str, float]:
    optimized_elapsed_ms: list[float] = []
    baseline_elapsed_ms: list[float] = []
    isfile_calls: list[float] = []

    with tempfile.TemporaryDirectory(prefix="melix-lora-processor-probe-") as temp_dir:
        base_model_dir = Path(temp_dir) / "base-model"
        _seed_base_model(base_model_dir, noise_count=noise_count, aux_index=noise_count)
        (base_model_dir / "tokenizer_config.json").write_text("{}\n", encoding="utf-8")
        (base_model_dir / "preprocessor_config.json").write_text("{}\n", encoding="utf-8")
        expected = _baseline_processor_resume_mode(base_model_dir)
        if expected != "preprocessor_config":
            raise RuntimeError("unexpected processor resume baseline")  # pragma: no cover

        original_isfile = metadata_module.os.path.isfile
        for _ in range(sample_count):
            call_count = 0

            def counting_isfile(path: str | Path):
                nonlocal call_count
                call_count += 1
                return original_isfile(path)

            metadata_module.os.path.isfile = counting_isfile
            started = time.perf_counter()
            try:
                optimized = metadata_module._processor_resume_mode(base_model_dir)
            finally:
                optimized_elapsed_ms.append((time.perf_counter() - started) * 1000.0)
                metadata_module.os.path.isfile = original_isfile
            if optimized != expected:
                raise RuntimeError("processor resume mode changed")  # pragma: no cover
            isfile_calls.append(float(call_count))

            started = time.perf_counter()
            baseline = _baseline_processor_resume_mode(base_model_dir)
            baseline_elapsed_ms.append((time.perf_counter() - started) * 1000.0)
            if baseline != expected:
                raise RuntimeError("processor resume baseline changed")  # pragma: no cover

    optimized_mean = statistics.fmean(optimized_elapsed_ms)
    baseline_mean = statistics.fmean(baseline_elapsed_ms)
    return {
        "processor_resume_baseline_elapsed_ms_mean": baseline_mean,
        "processor_resume_optimized_elapsed_ms_mean": optimized_mean,
        "processor_resume_delta_ms": optimized_mean - baseline_mean,
        "processor_resume_isfile_calls_mean": statistics.fmean(isfile_calls),
    }


def _baseline_quantized_kind_from_text(raw_value: str) -> str:
    normalized = raw_value.strip().lower()
    for kind in _QUANTIZED_KIND_ORDER:
        if re.search(rf"(?<![a-z0-9]){re.escape(kind)}(?![a-z0-9])", normalized):
            return kind
    return "unknown"


def _measure_quantized_kind(*, iteration_count: int, sample_count: int) -> dict[str, float]:
    payload = [
        "profile=mlx-community-q4",
        "source model 4bit adapter",
        "profile: optiq calibrated",
        "plain fused adapter",
        "8bit base checkpoint",
        "not-a-q4suffix",
    ] * max(1, iteration_count // 6)
    expected = [_baseline_quantized_kind_from_text(value) for value in payload]
    optimized_elapsed_ms: list[float] = []
    baseline_elapsed_ms: list[float] = []

    for _ in range(sample_count):
        started = time.perf_counter()
        optimized = [metadata_module._quantized_kind_from_text(value) for value in payload]
        optimized_elapsed_ms.append((time.perf_counter() - started) * 1000.0)

        started = time.perf_counter()
        baseline = [_baseline_quantized_kind_from_text(value) for value in payload]
        baseline_elapsed_ms.append((time.perf_counter() - started) * 1000.0)

        if optimized != expected or baseline != expected:
            raise RuntimeError("quantized kind parser output changed")

    optimized_mean = statistics.fmean(optimized_elapsed_ms)
    baseline_mean = statistics.fmean(baseline_elapsed_ms)
    return {
        "quantized_kind_baseline_elapsed_ms_mean": baseline_mean,
        "quantized_kind_optimized_elapsed_ms_mean": optimized_mean,
        "quantized_kind_delta_ms": optimized_mean - baseline_mean,
        "quantized_kind_iteration_count": float(len(payload)),
    }


def main() -> int:
    noise_count = _int_env("MELIX_LORA_AUX_MODULES_PROBE_NOISE_FILES", 4000)
    sample_count = _int_env("MELIX_LORA_AUX_MODULES_PROBE_SAMPLES", 7)
    quantized_iteration_count = _int_env("MELIX_LORA_QUANTIZED_KIND_PROBE_ITERATIONS", 12000)
    metrics = _measure(noise_count=noise_count, sample_count=sample_count)
    metrics.update(_measure_processor_resume_mode(noise_count=noise_count, sample_count=sample_count))
    metrics.update(
        _measure_quantized_kind(
            iteration_count=quantized_iteration_count,
            sample_count=sample_count,
        )
    )
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
