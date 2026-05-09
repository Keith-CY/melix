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


class _ProbeLoadedModel:
    runtime_kind = "rerank"
    runtime_model = {"model_id": "rerank-copy-probe"}


class _ProbeDocuments:
    def __init__(self, count: int) -> None:
        self._values = tuple(f"document-{index}" for index in range(count))
        self.iterations = 0

    def __iter__(self):
        self.iterations += 1
        return iter(self._values)


class _ProbeRuntime:
    def __init__(self, expected_documents: _ProbeDocuments) -> None:
        self.expected_documents = expected_documents
        self.document_identity_hits = 0

    def score_documents(self, loaded_model, query: str, documents) -> list[float]:
        if loaded_model != _ProbeLoadedModel.runtime_model:  # pragma: no cover - probe guard
            raise RuntimeError("unexpected loaded model payload")
        if query != "swift runtime":  # pragma: no cover - probe guard
            raise RuntimeError("unexpected query payload")
        self.document_identity_hits += int(documents is self.expected_documents)
        return [float(index) for index, _document in enumerate(documents)]


class _ProbeRegistry:
    def __init__(self, rerank_runtime: _ProbeRuntime) -> None:
        self.rerank_runtime = rerank_runtime

    def get_loaded_model(self, model_handle: str) -> _ProbeLoadedModel | None:
        if model_handle != "probe-model":  # pragma: no cover - probe guard
            return None
        return _ProbeLoadedModel()


class _ProbeRequest:
    def __init__(self, documents: _ProbeDocuments, *, top_k: int) -> None:
        self.model_handle = "probe-model"
        self.query = "swift runtime"
        self.documents = documents
        self.top_k = top_k


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


def _measure_request_document_passthrough(document_count: int, iteration_count: int) -> dict[str, float]:
    documents = _ProbeDocuments(document_count)
    runtime = _ProbeRuntime(documents)
    core = RerankCore(_ProbeRegistry(runtime))
    checksum = 0.0

    started = time.perf_counter()
    for _ in range(iteration_count):
        response = core.rerank(_ProbeRequest(documents, top_k=1))
        if response.error.code:  # pragma: no cover - probe guard
            raise RuntimeError(response.error.message)
        if len(response.items) != 1 or response.items[0].index != document_count - 1:  # pragma: no cover - probe guard
            raise RuntimeError("rerank request probe changed ranking semantics")
        checksum += response.items[0].score

    return {
        "request_elapsed_ms": round((time.perf_counter() - started) * 1000.0, 6),
        "request_document_count": float(document_count),
        "request_document_identity_hits": float(runtime.document_identity_hits),
        "request_document_iterations": float(documents.iterations),
        "request_iteration_count": float(iteration_count),
        "request_score_checksum": round(checksum, 6),
    }


def main() -> int:
    document_count = int(os.environ.get("MELIX_RERANK_TOP_K_PROBE_DOCUMENTS", "50000"))
    top_k = int(os.environ.get("MELIX_RERANK_TOP_K_PROBE_TOP_K", "1"))
    iteration_count = int(os.environ.get("MELIX_RERANK_TOP_K_PROBE_ITERATIONS", "120"))
    sample_count = int(os.environ.get("MELIX_RERANK_TOP_K_PROBE_SAMPLES", "7"))
    request_document_count = int(
        os.environ.get("MELIX_RERANK_REQUEST_PROBE_DOCUMENTS", str(document_count))
    )
    request_iteration_count = int(
        os.environ.get("MELIX_RERANK_REQUEST_PROBE_ITERATIONS", str(iteration_count))
    )
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
    metrics.update(
        _measure_request_document_passthrough(
            request_document_count,
            request_iteration_count,
        )
    )
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
