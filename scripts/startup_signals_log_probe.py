#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import tracemalloc
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

import worker.productization.startup_signals as startup_signals  # noqa: E402


def _write_logs(root: Path) -> dict[str, str | int]:
    control_plane_stderr = root / "control-plane.stderr.log"
    worker_stderr = root / "python-worker.stderr.log"
    noise = "boot line with enough content to make reads realistic\n" * 2500
    control_plane_stderr.write_text(noise + "fatal error: control plane crashed\n", encoding="utf-8")
    worker_stderr.write_text(noise + "Traceback: worker bootstrap failed\n", encoding="utf-8")
    return {
        "http_port": 11434,
        "ready_probe_url": "http://127.0.0.1:11434/v1/models",
        "control_plane_stderr_path": str(control_plane_stderr),
        "python_worker_stderr_path": str(worker_stderr),
    }


def _measure_case(
    manifest: dict[str, str | int],
    *,
    error_text: str,
    expected_classification: str,
    iterations: int,
) -> tuple[float, float, float]:
    original_reader: Callable[..., str] = startup_signals._read_last_nonempty_line
    original_exists = Path.exists
    read_count = 0
    exists_count = 0

    def tracked_reader(path: Path, *, chunk_size: int = 8192) -> str:
        nonlocal read_count
        read_count += 1
        return original_reader(path, chunk_size=chunk_size)

    def tracked_exists(path: Path) -> bool:
        nonlocal exists_count  # pragma: no cover
        exists_count += 1  # pragma: no cover
        return original_exists(path)  # pragma: no cover

    startup_signals._read_last_nonempty_line = tracked_reader
    Path.exists = tracked_exists
    try:
        started = time.perf_counter()
        for _ in range(iterations):
            report = startup_signals.classify_startup_failure(manifest, error_text=error_text)
            if report.classification != expected_classification:
                raise AssertionError(
                    f"expected {expected_classification}, got {report.classification}"
                )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
    finally:
        startup_signals._read_last_nonempty_line = original_reader
        Path.exists = original_exists
    return elapsed_ms, float(read_count), float(exists_count)


def _measure_tail_scan(log_path: Path, *, iterations: int) -> tuple[float, float]:
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    for _ in range(5):
        tracemalloc.start()
        started = time.perf_counter()
        for _ in range(iterations):
            line = startup_signals._read_last_nonempty_line(log_path, chunk_size=8192)
            if line != "final startup line":
                raise AssertionError(f"unexpected tail line: {line!r}")
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_samples.append(float(peak))
    return statistics.fmean(elapsed_samples), statistics.fmean(peak_samples)


def main() -> int:
    iterations = 400
    samples = 5
    conflict_elapsed: list[float] = []
    conflict_reads: list[float] = []
    conflict_exists: list[float] = []
    control_elapsed: list[float] = []
    control_reads: list[float] = []
    control_exists: list[float] = []
    worker_elapsed: list[float] = []
    worker_reads: list[float] = []
    worker_exists: list[float] = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        manifest = _write_logs(root)
        tail_log = root / "trailing-whitespace.log"
        tail_log.write_bytes(b"startup booted\nfinal startup line" + (b" \t\r\n" * 20000))
        for _ in range(samples):
            elapsed, reads, exists = _measure_case(
                manifest,
                error_text="bind() failed: Address already in use",
                expected_classification="host_port_conflict",
                iterations=iterations,
            )
            conflict_elapsed.append(elapsed)
            conflict_reads.append(reads / iterations)
            conflict_exists.append(exists / iterations)

            elapsed, reads, exists = _measure_case(
                manifest,
                error_text="handshake failed",
                expected_classification="control_plane_crash",
                iterations=iterations,
            )
            control_elapsed.append(elapsed)
            control_reads.append(reads / iterations)
            control_exists.append(exists / iterations)

            worker_manifest = dict(manifest)
            worker_manifest.pop("control_plane_stderr_path")
            elapsed, reads, exists = _measure_case(
                worker_manifest,
                error_text="handshake failed",
                expected_classification="worker_crash",
                iterations=iterations,
            )
            worker_elapsed.append(elapsed)
            worker_reads.append(reads / iterations)
            worker_exists.append(exists / iterations)

        tail_elapsed_mean, tail_peak_mean = _measure_tail_scan(tail_log, iterations=iterations)

    print(
        json.dumps(
            {
                "conflict_elapsed_ms_mean": round(statistics.fmean(conflict_elapsed), 6),
                "conflict_log_path_exists_checks_mean": round(statistics.fmean(conflict_exists), 6),
                "conflict_log_reads_mean": round(statistics.fmean(conflict_reads), 6),
                "control_crash_elapsed_ms_mean": round(statistics.fmean(control_elapsed), 6),
                "control_crash_log_path_exists_checks_mean": round(statistics.fmean(control_exists), 6),
                "control_crash_log_reads_mean": round(statistics.fmean(control_reads), 6),
                "iterations": float(iterations),
                "sample_count": float(samples),
                "tail_scan_elapsed_ms_mean": round(tail_elapsed_mean, 6),
                "tail_scan_peak_bytes_mean": round(tail_peak_mean, 6),
                "trailing_whitespace_bytes": float(80000),
                "worker_crash_elapsed_ms_mean": round(statistics.fmean(worker_elapsed), 6),
                "worker_crash_log_path_exists_checks_mean": round(statistics.fmean(worker_exists), 6),
                "worker_crash_log_reads_mean": round(statistics.fmean(worker_reads), 6),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
