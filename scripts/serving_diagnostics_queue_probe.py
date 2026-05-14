#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
import statistics
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.serving_diagnostics import (  # noqa: E402
    BoundedServingDiagnosticsEventQueue,
    ServingDiagnosticsEvent,
    ServingDiagnosticsRequestSummary,
    write_serving_diagnostics_bundle,
)


def main() -> int:
    capacity = int(os.environ.get("MELIX_SERVING_DIAGNOSTICS_QUEUE_CAPACITY", "64"))
    event_count = int(os.environ.get("MELIX_SERVING_DIAGNOSTICS_QUEUE_EVENTS", "4096"))
    sample_count = int(os.environ.get("MELIX_SERVING_DIAGNOSTICS_QUEUE_SAMPLES", "5"))
    elapsed_samples: list[float] = []
    serialization_samples: list[float] = []
    dropped = 0
    retained = 0
    serialized_bytes = 0
    serialization_checksum = 0
    summary = ServingDiagnosticsRequestSummary(
        request_id="req-probe",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    )
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
        with tempfile.TemporaryDirectory() as directory:
            paths = write_serving_diagnostics_bundle(
                output_root=Path(directory),
                bundle_id=f"diag-probe-{sample_index}",
                invocation={},
                effective_config={},
                model_refs={},
                request_summary=summary,
                events=snapshot,
                diagnostics_mode="debug",
            )
            event_rows = paths["events"].read_text(encoding="utf-8").splitlines()
            serialization_checksum = sum(
                int(json.loads(line)["event_index"]) for line in event_rows
            )
            serialized_bytes = paths["events"].stat().st_size
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
                "serialized_bytes": float(serialized_bytes),
                "dropped_count": float(dropped),
                "retained_count": float(retained),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
