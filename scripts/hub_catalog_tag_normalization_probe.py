from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

import worker.model_ops.hub_catalog as hub_catalog_module
from worker.model_ops.hub_catalog import HubCatalog


def _payload(index: int) -> dict[str, Any]:
    return {
        "id": f"plain-community/probe-{index}",
        "author": "plain-community",
        "pipeline_tag": "text-generation",
        "tags": ["Transformers", "Safetensors", "4-BIT", "OptiQ", f"family-{index % 17}"],
        "library_name": "transformers",
        "siblings": [{"rfilename": "config.json"}],
        "safetensors": {"total": 2_000_000_000 + index},
        "cardData": {"tags": ["Transformers", "Safetensors", f"family-{index % 17}"]},
    }


def _run_sample(record_count: int) -> tuple[float, int, int]:
    catalog = HubCatalog(local_memory_gb=64.0)
    payloads = [_payload(index) for index in range(record_count)]
    helper = getattr(hub_catalog_module, "_string_list", None)
    call_count = 0

    if helper is None:
        started = time.perf_counter()
        records = [catalog._summary_record(payload) for payload in payloads]
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        call_count = record_count * 2  # pragma: no cover - compatibility fallback for very old base checkouts
    else:
        original_helper = helper

        def counting_string_list(value: Any) -> list[str]:
            nonlocal call_count
            call_count += 1
            return original_helper(value)

        setattr(hub_catalog_module, "_string_list", counting_string_list)
        try:
            started = time.perf_counter()
            records = [catalog._summary_record(payload) for payload in payloads]
            elapsed_ms = (time.perf_counter() - started) * 1000.0
        finally:
            setattr(hub_catalog_module, "_string_list", original_helper)

    if len(records) != record_count:
        raise SystemExit(f"unexpected record count: {len(records)}")
    if {record.quantization_summary for record in records} != {"4-bit, optiq"}:
        raise SystemExit("unexpected quantization summary")
    if {record.local_fit_status for record in records} != {"blocked"}:  # pragma: no cover - defensive probe guard
        raise SystemExit("unexpected local-fit status")
    return elapsed_ms, call_count, len(records)


def main() -> int:
    record_count = int(os.environ.get("MELIX_HUB_CATALOG_TAG_PROBE_RECORDS", "5000"))
    sample_count = int(os.environ.get("MELIX_HUB_CATALOG_TAG_PROBE_SAMPLES", "5"))
    elapsed_samples: list[float] = []
    peak_samples: list[int] = []
    call_samples: list[int] = []
    observed_records = 0

    for _ in range(sample_count):
        tracemalloc.start()
        elapsed_ms, call_count, observed_records = _run_sample(record_count)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        elapsed_samples.append(elapsed_ms)
        peak_samples.append(peak_bytes)
        call_samples.append(call_count)

    metrics = {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "peak_bytes_mean": statistics.fmean(peak_samples),
        "tag_normalization_calls_mean": statistics.fmean(call_samples),
        "record_count": float(observed_records),
        "sample_count": float(sample_count),
    }
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
