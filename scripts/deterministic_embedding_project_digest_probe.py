#!/usr/bin/env python3
from __future__ import annotations

import gc
import json
from pathlib import Path
import sys
import time
import tracemalloc


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    repo_root = _repo_root()
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))

    from worker.runtime.embedding_backends import BERTEmbeddingBackend

    backend = BERTEmbeddingBackend()
    dimensions = 4096
    vector_count = 500
    sample_count = 3
    seed_texts = [f"bert::synthetic projection row {index % 251}::{index}" for index in range(vector_count)]
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    checksum = 0.0

    for _ in range(sample_count):
        gc.collect()
        tracemalloc.start()
        started = time.perf_counter()
        for seed_text in seed_texts:
            vector = backend._project_digest(seed_text, dimensions)
            if len(vector) != dimensions:
                raise AssertionError(f"unexpected vector length: {len(vector)}")
            checksum += vector[0] + vector[-1]
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        elapsed_samples.append(elapsed_ms)
        peak_samples.append(float(peak_bytes))

    payload = {
        "elapsed_ms_mean": round(sum(elapsed_samples) / len(elapsed_samples), 6),
        "peak_bytes_mean": round(sum(peak_samples) / len(peak_samples), 6),
        "sample_count": float(sample_count),
        "vector_count": float(vector_count),
        "dimensions": float(dimensions),
        "checksum": round(checksum, 6),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
