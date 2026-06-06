#!/usr/bin/env python3
from __future__ import annotations

import gc
import json
import os
from pathlib import Path
import sys
import time
import tracemalloc
from unittest.mock import patch


def _repo_root() -> Path:
    return Path(os.environ.get("MELIX_EMBEDDING_PROJECT_DIGEST_REPO_ROOT", Path.cwd())).resolve()


def main() -> int:
    repo_root = _repo_root()
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))

    from worker.runtime.embedding_backends import BERTEmbeddingBackend

    backend = BERTEmbeddingBackend()
    running_under_pytest = "PYTEST_CURRENT_TEST" in os.environ
    if running_under_pytest:
        with (
            patch("worker.runtime.embedding_backends._UNPACK_DIGEST_UINT32", lambda digest: (1,) * 8),
            patch("worker.runtime.embedding_backends._DIGEST_UINT32_SCALE", 1.0),
        ):
            assert backend._project_digest("bert::zero norm", 8) == [0.0] * 8

    dimensions = 4097
    default_dimensions = 8
    vector_count = 500
    default_vector_count = 5000
    sample_count = int(
        os.environ.get(
            "MELIX_EMBEDDING_PROJECT_DIGEST_SAMPLES",
            "3" if running_under_pytest else "9",
        )
    )
    seed_texts = [f"bert::synthetic projection row {index % 251}::{index}" for index in range(vector_count)]
    default_seed_texts = [
        f"bert::default projection row {index % 251}::{index}" for index in range(default_vector_count)
    ]
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    default_elapsed_samples: list[float] = []
    default_peak_samples: list[float] = []
    checksum = 0.0
    default_checksum = 0.0

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

        gc.collect()
        tracemalloc.start()
        default_started = time.perf_counter()
        for seed_text in default_seed_texts:
            vector = backend._project_digest(seed_text, default_dimensions)
            if len(vector) != default_dimensions:
                raise AssertionError(f"unexpected default vector length: {len(vector)}")
            default_checksum += vector[0] + vector[-1]
        default_elapsed_ms = (time.perf_counter() - default_started) * 1000.0
        _, default_peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        default_elapsed_samples.append(default_elapsed_ms)
        default_peak_samples.append(float(default_peak_bytes))

    payload = {
        "elapsed_ms_mean": round(sum(elapsed_samples) / len(elapsed_samples), 6),
        "peak_bytes_mean": round(sum(peak_samples) / len(peak_samples), 6),
        "default_dimension_elapsed_ms_mean": round(
            sum(default_elapsed_samples) / len(default_elapsed_samples),
            6,
        ),
        "default_dimension_peak_bytes_mean": round(
            sum(default_peak_samples) / len(default_peak_samples),
            6,
        ),
        "sample_count": float(sample_count),
        "vector_count": float(vector_count),
        "default_dimension_vector_count": float(default_vector_count),
        "dimensions": float(dimensions),
        "default_dimensions": float(default_dimensions),
        "checksum": round(checksum, 6),
        "default_dimension_checksum": round(default_checksum, 6),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
