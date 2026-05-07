#!/usr/bin/env python3
from __future__ import annotations

import gc
import json
import os
from pathlib import Path
import sys
import time
import tracemalloc

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.engine.rerank_core import RerankCore  # noqa: E402


def _legacy_rank_scores(scores: list[float], *, top_k: int | None) -> list[tuple[int, float]]:
    ranked = sorted(enumerate(scores), key=lambda item: (-item[1], item[0]))
    limit = top_k if top_k else len(ranked)
    if limit < len(ranked):
        ranked = ranked[:limit]
    return ranked


def _rank_scores(scores: list[float], *, top_k: int | None) -> list[tuple[int, float]]:
    ranker = getattr(RerankCore, "_rank_scores", None)
    if ranker is None:
        return _legacy_rank_scores(scores, top_k=top_k)
    return ranker(scores, top_k=top_k)


def _build_scores(document_count: int) -> list[float]:
    return [
        (((index * 7919) % 104729) / 104729.0) + (0.000001 * (index % 17))
        for index in range(document_count)
    ]


def main() -> int:
    document_count = int(os.environ.get("MELIX_RERANK_TOP_K_PROBE_DOCUMENTS", "50000"))
    top_k = int(os.environ.get("MELIX_RERANK_TOP_K_PROBE_TOP_K", "1"))
    iteration_count = int(os.environ.get("MELIX_RERANK_TOP_K_PROBE_ITERATIONS", "120"))
    sample_count = int(os.environ.get("MELIX_RERANK_TOP_K_PROBE_SAMPLES", "7"))
    scores = _build_scores(document_count)

    expected = _legacy_rank_scores(scores, top_k=top_k)
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    checksum = 0.0
    result_count = 0

    for _ in range(sample_count):
        gc.collect()
        tracemalloc.start()
        started = time.perf_counter()
        for _ in range(iteration_count):
            result = _rank_scores(scores, top_k=top_k)
            if result != expected:
                raise RuntimeError("top-k ranker changed ordering or tie-break semantics")
            result_count = len(result)
            checksum += sum((index + 1) * score for index, score in result)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_samples.append(float(peak))

    metrics = {
        "checksum": round(checksum, 6),
        "document_count": float(document_count),
        "elapsed_ms_mean": round(sum(elapsed_samples) / len(elapsed_samples), 6),
        "iteration_count": float(iteration_count),
        "peak_bytes_mean": round(sum(peak_samples) / len(peak_samples), 6),
        "result_count": float(result_count),
        "sample_count": float(sample_count),
        "top_k": float(top_k),
    }
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
