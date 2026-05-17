#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.probe_policy_overhead import measure_no_op_probe_policy_overhead  # noqa: E402


def main() -> int:
    iterations = int(os.environ.get("MELIX_PROBE_POLICY_OVERHEAD_ITERATIONS", "1000000"))
    samples = int(os.environ.get("MELIX_PROBE_POLICY_OVERHEAD_SAMPLES", "5"))
    threshold_pct = float(os.environ.get("MELIX_PROBE_POLICY_OVERHEAD_THRESHOLD_PCT", "5.0"))
    metrics = measure_no_op_probe_policy_overhead(
        iterations=iterations,
        samples=samples,
        threshold_pct=threshold_pct,
        absolute_tolerance_ms=float(
            os.environ.get("MELIX_PROBE_POLICY_OVERHEAD_ABSOLUTE_TOLERANCE_MS", "0.00002")
        ),
    ).to_dict()
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
