from __future__ import annotations

import json
import os
import shutil
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(os.environ.get("MELIX_SWIFT_BINARY_RESOLUTION_REPO_ROOT", Path.cwd())).resolve()
sys.path.insert(0, str(REPO_ROOT))

from tests.integration import helpers  # noqa: E402


def _write_executable(path: Path, mtime: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    os.utime(path, (mtime, mtime))


def _legacy_candidates(build_root: Path, product_name: str) -> list[Path]:
    candidates = [build_root / "debug" / product_name]
    candidates.extend(sorted(build_root.glob(f"*/debug/{product_name}")))
    return candidates


def _resolve_from_candidates(candidates: list[Path]) -> Path:
    executable_candidates = [
        candidate for candidate in candidates if candidate.is_file() and os.access(candidate, os.X_OK)
    ]
    if not executable_candidates:
        raise RuntimeError("probe fixture did not create executable candidates")
    return max(executable_candidates, key=lambda candidate: (candidate.stat().st_mtime, len(candidate.parts)))


def _run_once(root: Path, build_root: Path, product_name: str, *, legacy: bool) -> tuple[float, int, int]:
    tracemalloc.start()
    started = time.perf_counter()
    if legacy:
        resolved = _resolve_from_candidates(_legacy_candidates(build_root, product_name))
    else:
        resolved = helpers.resolve_swift_product_binary(
            root,
            package_path=Path("swift-probe"),
            product_name=product_name,
        )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if resolved.name != product_name:
        raise RuntimeError(f"unexpected product resolved: {resolved}")
    return elapsed_ms, peak, len(resolved.parts)


def collect_metrics() -> dict[str, float | int]:
    triples = int(os.environ.get("MELIX_SWIFT_BINARY_RESOLUTION_TRIPLES", "1500"))
    samples = int(os.environ.get("MELIX_SWIFT_BINARY_RESOLUTION_SAMPLES", "5"))
    product_name = "melix-probe"
    root = Path(tempfile.mkdtemp(prefix="melix-swift-binary-probe-"))
    try:
        build_root = root / "swift-probe" / ".build"
        _write_executable(build_root / "debug" / product_name, 1)
        for index in range(triples):
            triple = build_root / f"triple-{index:05d}" / "debug" / product_name
            _write_executable(triple, index + 2)

        new_elapsed: list[float] = []
        new_peaks: list[float] = []
        old_elapsed: list[float] = []
        old_peaks: list[float] = []
        for _ in range(samples):
            elapsed, peak, _ = _run_once(root, build_root, product_name, legacy=True)
            old_elapsed.append(elapsed)
            old_peaks.append(float(peak))
            elapsed, peak, _ = _run_once(root, build_root, product_name, legacy=False)
            new_elapsed.append(elapsed)
            new_peaks.append(float(peak))

        old_mean = statistics.fmean(old_elapsed)
        new_mean = statistics.fmean(new_elapsed)
        return {
            "candidate_count": triples + 1,
            "samples": samples,
            "legacy_elapsed_ms_mean": old_mean,
            "elapsed_ms_mean": new_mean,
            "delta_ms_mean": new_mean - old_mean,
            "legacy_peak_bytes_mean": statistics.fmean(old_peaks),
            "peak_bytes_mean": statistics.fmean(new_peaks),
            "peak_bytes_delta_mean": statistics.fmean(new_peaks) - statistics.fmean(old_peaks),
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> None:
    from scripts.integration_remove_tree_probe import collect_metrics as collect_remove_tree_metrics

    metrics = collect_metrics()
    metrics.update(collect_remove_tree_metrics())
    print(json.dumps(metrics, sort_keys=True))


if __name__ == "__main__":
    main()
