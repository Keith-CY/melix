from __future__ import annotations

import glob
import json
import os
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

repo_root_env = os.environ.get("MELIX_NATIVE_MTP_LOADER_REPO_ROOT")
repo_root = Path(repo_root_env) if repo_root_env else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))

try:
    from worker.runtime.native_mtp.mlx_lm_loader import _model_safetensor_files
except ImportError:  # Base revisions before this slice do not expose the helper.
    _model_safetensor_files = None


def _populate_model_dir(model_dir: Path, *, model_files: int, distractor_files: int) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    for index in range(model_files):
        (model_dir / f"model-{index:05d}-of-{model_files:05d}.safetensors").write_bytes(b"0")
    (model_dir / "model.safetensors").write_bytes(b"0")
    for index in range(distractor_files):
        (model_dir / f"mtp-{index:05d}.safetensors").write_bytes(b"0")
        (model_dir / f"model-{index:05d}.bin").write_bytes(b"0")
    (model_dir / "model-nested.safetensors").mkdir()


def _glob_model_safetensors(model_dir: Path) -> list[str]:
    files = glob.glob(str(model_dir / "model*.safetensors"))
    files.sort()
    return files


def _measure(callback, model_dir: Path, *, samples: int) -> tuple[list[float], list[float], int]:
    elapsed_ms: list[float] = []
    peaks: list[float] = []
    result_count = 0
    for _ in range(samples):
        tracemalloc.start()
        start = time.perf_counter()
        try:
            result = callback(model_dir)
        finally:
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        elapsed_ms.append((time.perf_counter() - start) * 1000.0)
        peaks.append(float(peak))
        result_count = len(result)
    return elapsed_ms, peaks, result_count


def run_probe() -> dict[str, float | int | str]:
    model_files = int(os.environ.get("MELIX_NATIVE_MTP_LOADER_MODEL_FILES", "1500"))
    distractor_files = int(os.environ.get("MELIX_NATIVE_MTP_LOADER_DISTRACTOR_FILES", "1500"))
    samples = int(os.environ.get("MELIX_NATIVE_MTP_LOADER_SAMPLES", "5"))
    with tempfile.TemporaryDirectory() as tmp:
        model_dir = Path(tmp) / "model"
        _populate_model_dir(
            model_dir,
            model_files=model_files,
            distractor_files=distractor_files,
        )
        baseline = _glob_model_safetensors(model_dir)
        candidate_callback = _model_safetensor_files or _glob_model_safetensors
        candidate = candidate_callback(model_dir)
        if baseline != candidate:
            raise SystemExit("candidate safetensor listing differs from glob baseline")
        old_ms, old_peaks, result_count = _measure(_glob_model_safetensors, model_dir, samples=samples)
        new_ms, new_peaks, _ = _measure(candidate_callback, model_dir, samples=samples)
    old_mean = statistics.mean(old_ms)
    new_mean = statistics.mean(new_ms)
    return {
        "result_count": result_count,
        "model_files": model_files,
        "distractor_files": distractor_files,
        "samples": samples,
        "old_mean_ms": old_mean,
        "new_mean_ms": new_mean,
        "delta_ms": new_mean - old_mean,
        "speedup": old_mean / new_mean if new_mean else 0.0,
        "old_peak_bytes_mean": statistics.mean(old_peaks),
        "new_peak_bytes_mean": statistics.mean(new_peaks),
    }


if __name__ == "__main__":
    print(json.dumps(run_probe(), sort_keys=True))
