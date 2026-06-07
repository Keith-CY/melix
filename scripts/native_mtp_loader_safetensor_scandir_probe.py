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
from typing import Any, Callable

repo_root_env = os.environ.get("MELIX_NATIVE_MTP_LOADER_REPO_ROOT")
repo_root = Path(repo_root_env) if repo_root_env else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))

try:
    from worker.runtime.native_mtp.mlx_lm_loader import (
        _is_mtp_weight_key,
        _load_json_payload,
        _load_weight_shards,
        _model_safetensor_files,
        extra_mtp_safetensor_files,
    )
except ImportError:  # Base revisions before this slice do not expose the helpers.
    extra_mtp_safetensor_files = None
    _is_mtp_weight_key = None
    _load_json_payload = None
    _load_weight_shards = None
    _model_safetensor_files = None


def _populate_model_dir(model_dir: Path, *, model_files: int, distractor_files: int) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    weight_map: dict[str, str] = {}
    for index in range(model_files):
        file_name = f"model-{index:05d}-of-{model_files:05d}.safetensors"
        (model_dir / file_name).write_bytes(b"0")
        weight_map[f"language_model.layers.{index}.weight"] = file_name
    (model_dir / "model.safetensors").write_bytes(b"0")
    for index in range(distractor_files):
        mtp_name = f"mtp-{index:05d}.safetensors"
        (model_dir / mtp_name).write_bytes(b"0")
        (model_dir / f"model-{index:05d}.bin").write_bytes(b"0")
        weight_map[f"language_model.mtp.layers.{index}.weight"] = mtp_name
        weight_map[f"language_model.mtp.layers.{index}.duplicate_weight"] = mtp_name
    (model_dir / "model-nested.safetensors").mkdir()
    (model_dir / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": weight_map}, sort_keys=True),
        encoding="utf-8",
    )


def _glob_model_safetensors(model_dir: Path) -> list[str]:
    files = glob.glob(str(model_dir / "model*.safetensors"))
    files.sort()
    return files


def _read_text_json_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _baseline_is_mtp_weight_key(key: Any) -> bool:
    value = str(key)
    return value.startswith("language_model.mtp.") or value.startswith("mtp.")


def _baseline_extra_mtp_safetensor_files(model_dir: Path) -> list[Path]:
    index_payload = _read_text_json_payload(model_dir / "model.safetensors.index.json")
    weight_map = index_payload.get("weight_map")
    if not isinstance(weight_map, dict):
        return []
    extra_files: list[Path] = []
    seen: set[Path] = set()
    for key, file_name in weight_map.items():
        value = str(key)
        if not (value.startswith("language_model.mtp.") or value.startswith("mtp.")):
            continue
        path = model_dir / str(file_name)
        if path.name.startswith("model") or path.suffix != ".safetensors":
            continue
        if path in seen or not path.exists():
            continue
        seen.add(path)
        extra_files.append(path)
    return extra_files


def _measure(
    callback: Callable[[Path], object],
    path: Path,
    *,
    samples: int,
    result_count_getter: Callable[[object], int] = len,
) -> tuple[list[float], list[float], int]:
    elapsed_ms: list[float] = []
    peaks: list[float] = []
    result_count = 0
    for _ in range(samples):
        tracemalloc.start()
        start = time.perf_counter()
        try:
            result = callback(path)
        finally:
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        elapsed_ms.append((time.perf_counter() - start) * 1000.0)
        peaks.append(float(peak))
        result_count = result_count_getter(result)
    return elapsed_ms, peaks, result_count


def _weight_map_count(result: object) -> int:
    if not isinstance(result, dict):
        return 0
    weight_map = result.get("weight_map")
    return len(weight_map) if isinstance(weight_map, dict) else 0


def _measure_key_predicate(
    callback: Callable[[Any], bool],
    keys: list[Any],
    *,
    samples: int,
    iterations: int,
) -> tuple[list[float], int]:
    elapsed_ms: list[float] = []
    expected_true_count = sum(1 for key in keys if _baseline_is_mtp_weight_key(key))
    for _ in range(samples):
        start = time.perf_counter()
        true_count = 0
        for _ in range(iterations):
            for key in keys:
                true_count += int(callback(key))
        elapsed_ms.append((time.perf_counter() - start) * 1000.0)
        if true_count != expected_true_count * iterations:
            raise RuntimeError("candidate native-MTP key predicate differs from baseline")
    return elapsed_ms, expected_true_count


def _baseline_load_weight_shards(
    load: Callable[[str], dict[str, str]],
    weight_files: list[str],
    extra_files: list[Path],
) -> dict[str, str]:
    weights: dict[str, str] = {}
    for wf in [*weight_files, *(str(path) for path in extra_files)]:
        weights.update(load(wf))
    return weights


def _candidate_load_weight_shards(
    load: Callable[[str], dict[str, str]],
    weight_files: list[str],
    extra_files: list[Path],
) -> dict[str, str]:
    if _load_weight_shards is None:
        return _baseline_load_weight_shards(load, weight_files, extra_files)
    return _load_weight_shards(load, weight_files, extra_files)


def _fake_weight_load(path: str) -> dict[str, str]:
    return {path: path}


def _measure_weight_loading(
    callback: Callable[[Callable[[str], dict[str, str]], list[str], list[Path]], dict[str, str]],
    weight_files: list[str],
    extra_files: list[Path],
    *,
    samples: int,
    iterations: int,
) -> tuple[list[float], list[float], int]:
    elapsed_ms: list[float] = []
    peaks: list[float] = []
    result_count = 0
    expected_count = len(weight_files) + len(extra_files)
    for _ in range(samples):
        tracemalloc.start()
        start = time.perf_counter()
        try:
            result: dict[str, str] = {}
            for _ in range(iterations):
                result = callback(_fake_weight_load, weight_files, extra_files)
        finally:
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        elapsed_ms.append((time.perf_counter() - start) * 1000.0)
        peaks.append(float(peak))
        result_count = len(result)
        if result_count != expected_count:
            raise RuntimeError("candidate native-MTP weight loading differs from baseline")
    return elapsed_ms, peaks, result_count


def run_probe() -> dict[str, float | int | str]:
    model_files = int(os.environ.get("MELIX_NATIVE_MTP_LOADER_MODEL_FILES", "1500"))
    distractor_files = int(os.environ.get("MELIX_NATIVE_MTP_LOADER_DISTRACTOR_FILES", "1500"))
    samples = int(os.environ.get("MELIX_NATIVE_MTP_LOADER_SAMPLES", "5"))
    key_iterations = int(os.environ.get("MELIX_NATIVE_MTP_LOADER_KEY_ITERATIONS", "2500"))
    weight_load_iterations = int(os.environ.get("MELIX_NATIVE_MTP_LOADER_WEIGHT_LOAD_ITERATIONS", "500"))
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
        model_listing_old_ms, model_listing_old_peaks, model_listing_result_count = _measure(
            _glob_model_safetensors,
            model_dir,
            samples=samples,
        )
        model_listing_new_ms, model_listing_new_peaks, _ = _measure(
            candidate_callback,
            model_dir,
            samples=samples,
        )

        index_path = model_dir / "model.safetensors.index.json"
        old_payload = _read_text_json_payload(index_path)
        payload_callback = _load_json_payload or _read_text_json_payload
        new_payload = payload_callback(index_path)
        if old_payload != new_payload:
            raise SystemExit("candidate native-MTP index JSON payload differs from read_text baseline")

        baseline_extra = _baseline_extra_mtp_safetensor_files(model_dir)
        extra_callback = extra_mtp_safetensor_files or _baseline_extra_mtp_safetensor_files
        candidate_extra = extra_callback(model_dir)
        if baseline_extra != candidate_extra:
            raise SystemExit("candidate native-MTP sidecar shard listing differs from baseline")

        old_ms, old_peaks, result_count = _measure(
            _read_text_json_payload,
            index_path,
            samples=samples,
            result_count_getter=_weight_map_count,
        )
        new_ms, new_peaks, _ = _measure(
            payload_callback,
            index_path,
            samples=samples,
            result_count_getter=_weight_map_count,
        )
        extra_old_ms, extra_old_peaks, extra_result_count = _measure(
            _baseline_extra_mtp_safetensor_files,
            model_dir,
            samples=samples,
        )
        extra_new_ms, extra_new_peaks, _ = _measure(
            extra_callback,
            model_dir,
            samples=samples,
        )
        key_candidates = [
            *old_payload["weight_map"].keys(),
            "mtp.direct.weight",
            "language_model.layers.0.weight",
        ]
        key_callback = _is_mtp_weight_key or _baseline_is_mtp_weight_key
        key_old_ms, key_true_count = _measure_key_predicate(
            _baseline_is_mtp_weight_key,
            key_candidates,
            samples=samples,
            iterations=key_iterations,
        )
        key_new_ms, _ = _measure_key_predicate(
            key_callback,
            key_candidates,
            samples=samples,
            iterations=key_iterations,
        )
        weight_load_old_ms, weight_load_old_peaks, weight_load_result_count = _measure_weight_loading(
            _baseline_load_weight_shards,
            list(candidate),
            candidate_extra,
            samples=samples,
            iterations=weight_load_iterations,
        )
        weight_load_new_ms, weight_load_new_peaks, _ = _measure_weight_loading(
            _candidate_load_weight_shards,
            list(candidate),
            candidate_extra,
            samples=samples,
            iterations=weight_load_iterations,
        )
    old_mean = statistics.mean(old_ms)
    new_mean = statistics.mean(new_ms)
    extra_old_mean = statistics.mean(extra_old_ms)
    extra_new_mean = statistics.mean(extra_new_ms)
    key_old_mean = statistics.mean(key_old_ms)
    key_new_mean = statistics.mean(key_new_ms)
    weight_load_old_mean = statistics.mean(weight_load_old_ms)
    weight_load_new_mean = statistics.mean(weight_load_new_ms)
    model_listing_old_mean = statistics.mean(model_listing_old_ms)
    model_listing_new_mean = statistics.mean(model_listing_new_ms)
    return {
        "result_count": result_count,
        "model_listing_result_count": model_listing_result_count,
        "extra_result_count": extra_result_count,
        "model_files": model_files,
        "distractor_files": distractor_files,
        "duplicate_mtp_entries": distractor_files,
        "samples": samples,
        "key_iterations": key_iterations,
        "weight_load_iterations": weight_load_iterations,
        "key_count": len(key_candidates),
        "key_true_count": key_true_count,
        "weight_load_result_count": weight_load_result_count,
        "weight_load_old_mean_ms": weight_load_old_mean,
        "weight_load_new_mean_ms": weight_load_new_mean,
        "weight_load_delta_ms": weight_load_new_mean - weight_load_old_mean,
        "weight_load_speedup": weight_load_old_mean / weight_load_new_mean if weight_load_new_mean else 0.0,
        "weight_load_old_peak_bytes_mean": statistics.mean(weight_load_old_peaks),
        "weight_load_new_peak_bytes_mean": statistics.mean(weight_load_new_peaks),
        "key_old_mean_ms": key_old_mean,
        "key_new_mean_ms": key_new_mean,
        "key_delta_ms": key_new_mean - key_old_mean,
        "key_speedup": key_old_mean / key_new_mean if key_new_mean else 0.0,
        "model_listing_old_mean_ms": model_listing_old_mean,
        "model_listing_new_mean_ms": model_listing_new_mean,
        "model_listing_delta_ms": model_listing_new_mean - model_listing_old_mean,
        "model_listing_speedup": model_listing_old_mean / model_listing_new_mean
        if model_listing_new_mean
        else 0.0,
        "model_listing_old_peak_bytes_mean": statistics.mean(model_listing_old_peaks),
        "model_listing_new_peak_bytes_mean": statistics.mean(model_listing_new_peaks),
        "old_mean_ms": old_mean,
        "new_mean_ms": new_mean,
        "delta_ms": new_mean - old_mean,
        "speedup": old_mean / new_mean if new_mean else 0.0,
        "old_peak_bytes_mean": statistics.mean(old_peaks),
        "new_peak_bytes_mean": statistics.mean(new_peaks),
        "extra_old_mean_ms": extra_old_mean,
        "extra_new_mean_ms": extra_new_mean,
        "extra_delta_ms": extra_new_mean - extra_old_mean,
        "extra_speedup": extra_old_mean / extra_new_mean if extra_new_mean else 0.0,
        "extra_old_peak_bytes_mean": statistics.mean(extra_old_peaks),
        "extra_new_peak_bytes_mean": statistics.mean(extra_new_peaks),
    }


if __name__ == "__main__":
    print(json.dumps(run_probe(), sort_keys=True))
