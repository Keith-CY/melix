#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(os.environ.get("MELIX_REPORT_EVIDENCE_GATE_REPO_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.productization.report_evidence_gate import _rule_matches_report  # noqa: E402


def _measure(iterations: int, sample_count: int) -> dict[str, float]:
    run_kinds = tuple(f"probe_kind_{index}" for index in range(64)) + ("target_kind",)
    run_kind_rule = {"run_kinds": run_kinds}
    runs = [{"run_kind": f"observed_kind_{index}"} for index in range(79)] + [{"run_kind": "target_kind"}]
    metric_prefixes = tuple(f"adapter.probe_{index}." for index in range(16)) + ("adapter.target.",)
    target_fields = tuple(f"adapter_field_{index}" for index in range(16)) + ("adapter_target",)
    tuple_rule = {"metric_prefixes": metric_prefixes, "target_fields": target_fields}
    metrics = [{"metric": f"runtime.probe_{index}.latency_ms"} for index in range(47)] + [
        {"metric": "adapter.target.latency_ms"}
    ]
    targets = [{"unused": ""} for _ in range(16)] + [{"adapter_target": "adapter-a"}]
    elapsed_samples: list[float] = []
    match_count = 0

    for _ in range(sample_count):
        started = time.perf_counter()
        for _index in range(iterations):
            if not _rule_matches_report(
                rule=run_kind_rule,
                runs=runs,
                targets=[],
                metrics=[],
                probe_phases=set(),
            ):
                raise RuntimeError("expected run-kind rule to match target run")
            if not _rule_matches_report(
                rule=tuple_rule,
                runs=[],
                targets=targets,
                metrics=metrics,
                probe_phases=set(),
            ):
                raise RuntimeError("expected tuple-backed metric/target rule to match")
            match_count += 2
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "iterations": float(iterations),
        "sample_count": float(sample_count),
        "run_kind_count": float(len(run_kinds)),
        "runs_per_call": float(len(runs)),
        "metric_prefix_count": float(len(metric_prefixes)),
        "target_field_count": float(len(target_fields)),
        "match_count": float(match_count),
    }


def main() -> int:
    iterations = int(os.environ.get("MELIX_REPORT_EVIDENCE_RUN_KIND_ITERATIONS", "50000"))
    sample_count = int(os.environ.get("MELIX_REPORT_EVIDENCE_RUN_KIND_SAMPLES", "5"))
    print(json.dumps(_measure(iterations, sample_count), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
