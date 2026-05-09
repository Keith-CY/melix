from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.productization.run_evidence import RunEvidenceProbe, summarize_probe_timeline


def _build_probes(probe_count: int) -> list[RunEvidenceProbe]:
    return [
        RunEvidenceProbe(
            run_id="probe-summary",
            trace_id="probe-summary:trace",
            span_id=f"probe-summary:span-{index}",
            parent_span_id="probe-summary:parent",
            component="runtime" if index % 3 else "worker",
            phase=f"phase-{index % 97}",
            started_at_monotonic_ms=index,
            duration_ms=float((index * 37) % 1000) + (0.001 * (index % 11)),
            status="completed",
        )
        for index in range(probe_count)
    ]


def main() -> int:
    probe_count = int(os.environ.get("MELIX_RUN_EVIDENCE_PROBE_COUNT", "100000"))
    sample_count = int(os.environ.get("MELIX_RUN_EVIDENCE_PROBE_SAMPLES", "5"))
    probes = _build_probes(probe_count)
    elapsed_ms: list[float] = []
    peak_bytes: list[float] = []
    checksum = 0
    for _ in range(sample_count):
        tracemalloc.start()
        started = time.perf_counter()
        summary = summarize_probe_timeline(probes)
        elapsed_ms.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        peak_bytes.append(float(peak))
        tracemalloc.stop()
        slowest = summary.get("slowest_phases", [])
        if len(slowest) != 5:
            raise SystemExit(f"unexpected slowest phase count: {len(slowest)}")
        checksum = sum(len(str(row.get("span_id", ""))) for row in slowest)
    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed_ms),
                "peak_bytes_mean": statistics.fmean(peak_bytes),
                "probe_count": float(probe_count),
                "sample_count": float(sample_count),
                "slowest_count": 5.0,
                "checksum": float(checksum),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
