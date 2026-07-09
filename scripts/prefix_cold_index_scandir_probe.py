#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("MELIX_PREFIX_COLD_INDEX_REPO_ROOT", Path.cwd()))
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime import prefix_block_store as target  # noqa: E402
from worker.runtime.prefix_block_store import ColdPrefixStore  # noqa: E402


def _fake_serializer(cache_snapshot: Any, path: Path) -> None:
    path.write_text(json.dumps(cache_snapshot), encoding="utf-8")


def _fake_deserializer(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_cold_index(root: Path, *, entry_count: int) -> None:
    cold = ColdPrefixStore(root, serializer=_fake_serializer, deserializer=_fake_deserializer)
    for index in range(entry_count):
        ok = cold.store(
            session_id=f"session-{index:05d}",
            token_ids=[index, index + 1, index + 2, index + 3],
            cache_snapshot=[{"data": index}],
            cache_mode="CACHE_MODE_TIERED",
            model_id="m1",
            model_revision="r1",
            block_size=4,
            acceleration_mode="",
        )
        if not ok:
            raise RuntimeError(f"failed to build cold entry {index}")
    (root / "ignored.tmp").write_text("ignored\n", encoding="utf-8")
    (root / "nested.meta.json").mkdir()


def measure(*, entry_count: int, samples: int) -> dict[str, float]:
    elapsed_ms: list[float] = []
    loaded_counts: list[float] = []
    scandir_calls: list[float] = []
    path_glob_calls: list[float] = []
    original_scandir = target.os.scandir
    original_glob = target.Path.glob

    with tempfile.TemporaryDirectory(prefix="melix-prefix-cold-index-") as tmp:
        root = Path(tmp) / "cold"
        _build_cold_index(root, entry_count=entry_count)
        try:
            for _ in range(samples):
                sample_scandir_calls = 0
                sample_path_glob_calls = 0

                def counted_scandir(path: str | os.PathLike[str]):
                    nonlocal sample_scandir_calls
                    sample_scandir_calls += 1
                    return original_scandir(path)

                def counted_glob(self: Path, pattern: str):
                    nonlocal sample_path_glob_calls
                    sample_path_glob_calls += 1
                    return original_glob(self, pattern)

                target.os.scandir = counted_scandir
                target.Path.glob = counted_glob
                cold = ColdPrefixStore(root, serializer=_fake_serializer, deserializer=_fake_deserializer)
                started = time.perf_counter()
                loaded = cold.entry_count()
                elapsed_ms.append((time.perf_counter() - started) * 1000.0)
                loaded_counts.append(float(loaded))
                scandir_calls.append(float(sample_scandir_calls))
                path_glob_calls.append(float(sample_path_glob_calls))
                if loaded != entry_count:
                    raise RuntimeError(f"unexpected loaded count: {loaded} != {entry_count}")
        finally:
            target.os.scandir = original_scandir
            target.Path.glob = original_glob

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_ms),
        "elapsed_ms_min": min(elapsed_ms),
        "elapsed_ms_p95": sorted(elapsed_ms)[int((len(elapsed_ms) - 1) * 0.95)],
        "entry_count": float(entry_count),
        "loaded_count_mean": statistics.fmean(loaded_counts),
        "path_glob_calls_mean": statistics.fmean(path_glob_calls),
        "sample_count": float(samples),
        "scandir_calls_mean": statistics.fmean(scandir_calls),
    }


def main() -> int:
    entry_count = int(os.environ.get("MELIX_PREFIX_COLD_INDEX_PROBE_ENTRIES", "600"))
    samples = int(os.environ.get("MELIX_PREFIX_COLD_INDEX_PROBE_SAMPLES", "7"))
    print(json.dumps(measure(entry_count=entry_count, samples=samples), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
