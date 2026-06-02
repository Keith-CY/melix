#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "mlx-worker-python"))

from worker.productization.gemma_e4b_profile_gate import (  # noqa: E402
    default_passing_evidence,
    evaluate_gemma_e4b_profile_gate_evidence,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate Gemma E4B selected-profile release-gate evidence."
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Read a persisted Gemma E4B profile-gate evidence JSON payload.",
    )
    parser.add_argument(
        "--metrics",
        action="store_true",
        help="Emit flat numeric metrics for the PR-scoped performance runner.",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=5,
        help="Number of evaluation timing samples to include in --metrics output.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=2000,
        help="Gate evaluations per timing sample for --metrics output.",
    )
    return parser.parse_args()


def load_evidence(path: Path | None) -> dict[str, Any]:
    if path is None:
        return default_passing_evidence()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Gemma E4B profile gate evidence must be a JSON object")
    return payload


def collect_metrics(evidence: dict[str, Any], *, samples: int, iterations: int) -> dict[str, float]:
    if samples < 1:
        raise ValueError("--samples must be at least 1")
    if iterations < 1:
        raise ValueError("--iterations must be at least 1")

    elapsed_ms: list[float] = []
    report: dict[str, Any] | None = None
    for _ in range(samples):
        started = time.perf_counter()
        for _ in range(iterations):
            report = evaluate_gemma_e4b_profile_gate_evidence(evidence)
        elapsed_ms.append((time.perf_counter() - started) * 1000.0)

    assert report is not None
    metrics = dict(report["metrics"])
    metrics["elapsed_ms_mean"] = statistics.fmean(elapsed_ms)
    metrics["iteration_count"] = float(iterations)
    metrics["sample_count"] = float(samples)
    return metrics


def main() -> int:
    args = parse_args()
    evidence = load_evidence(args.input)
    report = evaluate_gemma_e4b_profile_gate_evidence(evidence)
    if args.metrics:
        print(
            json.dumps(
                collect_metrics(evidence, samples=args.samples, iterations=args.iterations),
                sort_keys=True,
            )
        )
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
