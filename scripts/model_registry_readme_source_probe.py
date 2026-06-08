from __future__ import annotations

import json
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.model_registry.catalog import _gemma4_qat_source_model


def _legacy_source_model(readme_text: str, *, model_size: str, companion: bool) -> str:
    for line in readme_text.splitlines():
        stripped = line.strip().strip("'\"")
        if stripped.startswith("base_model:"):
            value = stripped.split(":", 1)[1].strip().strip("'\"[] ")
            if value:
                return value

    size_name = {
        "e2b": "E2B",
        "e4b": "E4B",
        "12b": "12B",
        "26b-a4b": "26B-A4B",
    }.get(model_size)
    if not size_name:
        return ""
    suffix = "-assistant" if companion else ""
    return f"google/gemma-4-{size_name}-it-qat-q4_0-unquantized{suffix}"


def _readme_with_late_base_model(line_count: int) -> str:
    lines = [
        "---",
        "library_name: mlx",
        "tags:",
    ]
    lines.extend(f"- metadata-line-{index:05d}" for index in range(line_count))
    lines.append("  'base_model: [google/gemma-4-E4B-it-qat-q4_0-unquantized]'")
    lines.append("---")
    lines.append("Optimized model card body")
    return "\n".join(lines)


def _measure(function, readme_text: str, *, iterations: int, samples: int) -> tuple[float, float, str]:
    elapsed_values: list[float] = []
    peak_values: list[int] = []
    result = ""
    for _ in range(samples):
        tracemalloc.start()
        start = time.perf_counter()
        for _ in range(iterations):
            result = function(readme_text, model_size="e4b", companion=False)
        elapsed = (time.perf_counter() - start) * 1000
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        elapsed_values.append(elapsed / iterations)
        peak_values.append(peak)
    return statistics.mean(elapsed_values), statistics.mean(peak_values), result


def run_probe(*, line_count: int = 5000, iterations: int = 250, samples: int = 5) -> dict[str, float]:
    readme_text = _readme_with_late_base_model(line_count)
    old_mean, old_peak, old_result = _measure(
        _legacy_source_model,
        readme_text,
        iterations=iterations,
        samples=samples,
    )
    new_mean, new_peak, new_result = _measure(
        _gemma4_qat_source_model,
        readme_text,
        iterations=iterations,
        samples=samples,
    )
    expected = "google/gemma-4-E4B-it-qat-q4_0-unquantized"
    if old_result != expected or new_result != expected:
        raise AssertionError(f"unexpected source model results: old={old_result!r} new={new_result!r}")
    return {
        "old_elapsed_ms_mean": old_mean,
        "new_elapsed_ms_mean": new_mean,
        "delta_ms": new_mean - old_mean,
        "speedup": old_mean / new_mean if new_mean else 0.0,
        "old_peak_bytes_mean": old_peak,
        "new_peak_bytes_mean": new_peak,
        "line_count": float(line_count),
        "iterations": float(iterations),
        "samples": float(samples),
    }


if __name__ == "__main__":
    print(json.dumps(run_probe(), sort_keys=True))
