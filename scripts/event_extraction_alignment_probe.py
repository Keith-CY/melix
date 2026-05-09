from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return int(raw)


def _build_sparse_matrix(size: int, accepted_per_row: int) -> tuple[list[list[float]], list[list[bool]]]:
    scores: list[list[float]] = []
    accepted: list[list[bool]] = []
    for gold_index in range(size):
        score_row = [0.0] * size
        accepted_row = [False] * size
        for edge_index in range(accepted_per_row):
            pred_index = (gold_index * 5 + edge_index * 3) % size
            accepted_row[pred_index] = True
            # Keep a deterministic spread of positive weights with stable tie behavior.
            score_row[pred_index] = 0.5 + (((gold_index + 1) * (edge_index + 3)) % 41) / 100.0
        scores.append(score_row)
        accepted.append(accepted_row)
    return scores, accepted


def main() -> int:
    repo_root = Path.cwd()
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))

    from worker.productization.event_extraction import (  # noqa: PLC0415
        _accepted_event_matching_edges,
        _maximum_weight_event_matching,
        _string_similarity,
    )

    size = _int_env("MELIX_EVENT_ALIGNMENT_PROBE_SIZE", 14)
    accepted_per_row = _int_env("MELIX_EVENT_ALIGNMENT_PROBE_ACCEPTED_PER_ROW", 2)
    iterations = _int_env("MELIX_EVENT_ALIGNMENT_PROBE_ITERATIONS", 20)
    sample_count = _int_env("MELIX_EVENT_ALIGNMENT_PROBE_SAMPLES", 5)
    scores, accepted = _build_sparse_matrix(size, accepted_per_row)
    expected_edge_count = sum(sum(row) for row in accepted)
    edge_count = sum(len(row) for row in _accepted_event_matching_edges(scores, accepted))
    if edge_count != expected_edge_count:
        raise RuntimeError(f"unexpected accepted edge count: {edge_count} != {expected_edge_count}")

    expected_matches = _maximum_weight_event_matching(scores, accepted)
    expected_checksum = sum((gold + 1) * 1000 + (pred + 1) * 10 + score for gold, pred, score in expected_matches)

    elapsed_samples: list[float] = []
    checksum = 0.0
    match_count = 0
    for _sample_index in range(sample_count):
        started = time.perf_counter()
        for _iteration in range(iterations):
            matches = _maximum_weight_event_matching(scores, accepted)
            checksum += sum((gold + 1) * 1000 + (pred + 1) * 10 + score for gold, pred, score in matches)
            match_count += len(matches)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)

    expected_total_checksum = expected_checksum * iterations * sample_count
    if abs(checksum - expected_total_checksum) > 1e-6:
        raise RuntimeError(f"unexpected matching checksum: {checksum} != {expected_total_checksum}")

    similarity_pairs = [
        (f"Delivered supply crate {index % 32}", f"delivered supply crates {index % 32}")
        for index in range(512)
    ]
    similarity_elapsed_samples: list[float] = []
    similarity_checksum = 0.0
    for _sample_index in range(sample_count):
        started = time.perf_counter()
        for _iteration in range(iterations):
            for left, right in similarity_pairs:
                similarity_checksum += _string_similarity(left, right)
        similarity_elapsed_samples.append((time.perf_counter() - started) * 1000.0)

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed_samples),
                "elapsed_ms_min": min(elapsed_samples),
                "similarity_elapsed_ms_mean": statistics.fmean(similarity_elapsed_samples),
                "similarity_elapsed_ms_min": min(similarity_elapsed_samples),
                "similarity_pair_count": float(len(similarity_pairs)),
                "similarity_checksum": similarity_checksum,
                "matrix_size": float(size),
                "accepted_edges": float(edge_count),
                "iterations_per_sample": float(iterations),
                "sample_count": float(sample_count),
                "match_count_mean": match_count / sample_count,
                "checksum": checksum,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
