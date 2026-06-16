#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path


def _load_snapshot_module(repo_root: Path):
    module_path = repo_root / "scripts" / "melix_metrics_snapshot.py"
    spec = importlib.util.spec_from_file_location("melix_metrics_snapshot_probe", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    repo_root = Path.cwd()
    module = _load_snapshot_module(repo_root)
    file_count = 4000
    noise_count = 200
    sample_count = 9
    elapsed_samples: list[float] = []
    with tempfile.TemporaryDirectory(prefix="melix-pr-perf-metrics-snapshot-") as temp_dir:
        runtime_dir = Path(temp_dir) / "runtime"
        runtime_dir.mkdir()
        expected_control = runtime_dir / "control-plane-metrics-latest.json"
        expected_swift = runtime_dir / "swift-text-worker-metrics-latest.json"
        expected_python = runtime_dir / "python-worker-metrics-latest.json"
        for index in range(file_count):
            path = runtime_dir / f"control-plane-metrics-{index:04d}.json"
            path.write_text('{"values":{"control_plane.text_first_load_ms":1}}', encoding="utf-8")
            stamp = 1_000_000 + index
            path.touch()
            path.chmod(0o600)
            path_stat_time = stamp / 1000.0
            os.utime(path, (path_stat_time, path_stat_time))
        expected_control.write_text('{"values":{"control_plane.text_first_load_ms":2}}', encoding="utf-8")
        os.utime(expected_control, (2_000_000, 2_000_000))
        for index in range(noise_count):
            path = runtime_dir / f"swift-text-worker-metrics-{index:04d}.json"
            path.write_text('{"values":{"swift_text.prefill_ms":1}}', encoding="utf-8")
            stamp = 1_500_000 + index
            os.utime(path, (stamp, stamp))
        expected_swift.write_text('{"values":{"swift_text.prefill_ms":2}}', encoding="utf-8")
        os.utime(expected_swift, (2_500_000, 2_500_000))
        expected_python.write_text('{"values":{"python_worker.bootstrap_ms":3}}', encoding="utf-8")
        os.utime(expected_python, (3_000_000, 3_000_000))
        resolved = {}
        for _ in range(sample_count):
            started = time.perf_counter()
            resolved = module.resolve_source_paths(runtime_dir=runtime_dir, environment={})
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)

    expected_paths = {
        "control_plane": expected_control,
        "swift_text_worker": expected_swift,
        "python_worker": expected_python,
    }
    resolved_paths = {name: source.path for name, source in resolved.items()}
    if resolved_paths != expected_paths:
        raise AssertionError(f"expected {expected_paths}, got {resolved_paths}")
    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "sample_count": float(sample_count),
                "file_count": float(file_count),
                "noise_count": float(noise_count),
                "source_count": float(len(expected_paths)),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
