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

REPO_ROOT = Path(os.environ.get("MELIX_REMOVE_TREE_REPO_ROOT", Path.cwd())).resolve()
sys.path.insert(0, str(REPO_ROOT))

from tests.integration import helpers  # noqa: E402


def _populate_tree(root: Path, *, directory_count: int, files_per_directory: int) -> None:
    for index in range(directory_count):
        nested = root / f"group-{index // 100:04d}" / f"leaf-{index:05d}"
        nested.mkdir(parents=True, exist_ok=True)
        for file_index in range(files_per_directory):
            (nested / f"state-{file_index:02d}.json").write_text("{}\n", encoding="utf-8")


def _legacy_remove_tree(root: Path) -> None:
    if not root.exists():
        return
    for child in sorted(root.rglob("*"), reverse=True):
        if child.is_file() or child.is_symlink():
            child.unlink(missing_ok=True)
        else:
            child.rmdir()
    root.rmdir()


def _new_remove_tree(root: Path) -> None:
    stack = helpers.LiveMelixStack.__new__(helpers.LiveMelixStack)
    stack._remove_tree(root)


def _run_once(base: Path, *, directory_count: int, files_per_directory: int, legacy: bool) -> tuple[float, int]:
    root = base / ("legacy" if legacy else "new")
    _populate_tree(root, directory_count=directory_count, files_per_directory=files_per_directory)
    tracemalloc.start()
    started = time.perf_counter()
    if legacy:
        _legacy_remove_tree(root)
    else:
        _new_remove_tree(root)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if root.exists():
        raise RuntimeError(f"cleanup root still exists: {root}")
    return elapsed_ms, peak


def collect_metrics() -> dict[str, float | int]:
    directory_count = int(os.environ.get("MELIX_REMOVE_TREE_DIRECTORIES", "1200"))
    files_per_directory = int(os.environ.get("MELIX_REMOVE_TREE_FILES_PER_DIRECTORY", "2"))
    samples = int(os.environ.get("MELIX_REMOVE_TREE_SAMPLES", "5"))
    base = Path(tempfile.mkdtemp(prefix="melix-remove-tree-probe-"))
    try:
        old_elapsed: list[float] = []
        old_peaks: list[float] = []
        new_elapsed: list[float] = []
        new_peaks: list[float] = []
        for sample_index in range(samples):
            sample_base = base / f"sample-{sample_index:02d}"
            sample_base.mkdir()
            elapsed, peak = _run_once(
                sample_base,
                directory_count=directory_count,
                files_per_directory=files_per_directory,
                legacy=True,
            )
            old_elapsed.append(elapsed)
            old_peaks.append(float(peak))
            elapsed, peak = _run_once(
                sample_base,
                directory_count=directory_count,
                files_per_directory=files_per_directory,
                legacy=False,
            )
            new_elapsed.append(elapsed)
            new_peaks.append(float(peak))

        old_mean = statistics.fmean(old_elapsed)
        new_mean = statistics.fmean(new_elapsed)
        return {
            "remove_tree_directories": directory_count,
            "remove_tree_files_per_directory": files_per_directory,
            "remove_tree_samples": samples,
            "remove_tree_legacy_elapsed_ms_mean": old_mean,
            "remove_tree_elapsed_ms_mean": new_mean,
            "remove_tree_delta_ms_mean": new_mean - old_mean,
            "remove_tree_legacy_peak_bytes_mean": statistics.fmean(old_peaks),
            "remove_tree_peak_bytes_mean": statistics.fmean(new_peaks),
            "remove_tree_peak_bytes_delta_mean": statistics.fmean(new_peaks) - statistics.fmean(old_peaks),
        }
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main() -> None:
    print(json.dumps(collect_metrics(), sort_keys=True))


if __name__ == "__main__":
    main()
