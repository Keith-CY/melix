#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.serving_diagnostics import (  # noqa: E402
    BoundedServingDiagnosticsEventQueue,
    ServingDiagnosticsEvent,
)


def main() -> int:
    capacity = int(os.environ.get("MELIX_SERVING_DIAGNOSTICS_QUEUE_CAPACITY", "64"))
    event_count = int(os.environ.get("MELIX_SERVING_DIAGNOSTICS_QUEUE_EVENTS", "4096"))
    sample_count = int(os.environ.get("MELIX_SERVING_DIAGNOSTICS_QUEUE_SAMPLES", "5"))
    elapsed_samples: list[float] = []
    serialization_samples: list[float] = []
    dropped = 0
    retained = 0
    serialization_checksum = 0
    for sample_index in range(max(sample_count, 1)):
        queue = BoundedServingDiagnosticsEventQueue(max_events=capacity)
        started = time.perf_counter()
        for event_index in range(max(event_count, 1)):
            queue.append(
                ServingDiagnosticsEvent(
                    request_id=f"req-{sample_index}",
                    phase="decode",
                    event_index=event_index,
                    status="completed",
                    duration_ms=0.001,
                )
            )
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        snapshot = queue.snapshot()
        dropped = snapshot.dropped_count
        retained = len(snapshot.events)
        serialize_started = time.perf_counter()
        checksum = 0
        for event in snapshot.events:
            checksum += int(event.to_dict()["event_index"])
        serialization_checksum = checksum
        serialization_samples.append((time.perf_counter() - serialize_started) * 1000.0)
    print(
        json.dumps(
            {
                "capacity": float(capacity),
                "event_count": float(event_count),
                "sample_count": float(max(sample_count, 1)),
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "serialization_elapsed_ms_mean": round(statistics.fmean(serialization_samples), 6),
                "serialization_checksum": float(serialization_checksum),
                "dropped_count": float(dropped),
                "retained_count": float(retained),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
