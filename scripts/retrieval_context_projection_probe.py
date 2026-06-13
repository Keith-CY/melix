#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("MELIX_RETRIEVAL_CONTEXT_PROJECTION_REPO_ROOT", Path.cwd()))
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime import retrieval_context as rc  # noqa: E402
from worker.runtime.prompt_context import PromptContextAdmission  # noqa: E402


def _entry_count() -> int:
    value = os.environ.get("MELIX_RETRIEVAL_CONTEXT_PROJECTION_ENTRIES", "96")
    try:
        count = int(value)
    except ValueError:
        return 96
    return max(1, count)


def _samples() -> int:
    value = os.environ.get("MELIX_RETRIEVAL_CONTEXT_PROJECTION_SAMPLES", "7")
    try:
        count = int(value)
    except ValueError:
        return 7
    return max(1, count)


def _iterations() -> int:
    value = os.environ.get("MELIX_RETRIEVAL_CONTEXT_PROJECTION_ITERATIONS", "400")
    try:
        count = int(value)
    except ValueError:
        return 400
    return max(1, count)


def _build_entries(count: int) -> list[rc.RetrievalContextEntry]:
    return [
        rc.RetrievalContextEntry(
            context_kind="retrieved_document" if index % 2 == 0 else "retrieved_image",
            source_id=f"source:{index}",
            payload={"index": index, "text": f"retrieved payload {index}"},
            owner_scope_checked=True,
            segment_id=f"search:result-{index}",
            source_field=f"retrieved_context_{index}",
            reason="retrieved result is prompt data, not instructions",
            corrective_action="Keep retrieved results in user-role prompt context.",
        )
        for index in range(count)
    ]


def _build_store_records(entries: Iterable[rc.RetrievalContextEntry]) -> list[dict[str, Any]]:
    return [
        {
            "context_kind": entry.context_kind,
            "source_id": entry.source_id,
            "payload": entry.payload,
            "owner_scope_checked": entry.owner_scope_checked,
            "segment_id": entry.segment_id,
            "source_field": entry.source_field,
            "reason": entry.reason,
            "corrective_action": entry.corrective_action,
        }
        for entry in entries
    ]


def _build_admissions(entries: Iterable[rc.RetrievalContextEntry]) -> dict[str, PromptContextAdmission]:
    admissions: dict[str, PromptContextAdmission] = {}
    for entry in entries:
        admissions[entry.source_id] = PromptContextAdmission(
            user_payload={entry.source_field: entry.payload},
            untrusted_context_receipts=[
                {
                    "source_type": entry.context_kind,
                    "source_field": entry.source_field,
                    "source_id": entry.source_id,
                    "segment_id": entry.segment_id,
                    "owner_scope_checked": entry.owner_scope_checked,
                }
            ],
        )
    return admissions


def _baseline_project_retrieval_contexts(
    entries: list[rc.RetrievalContextEntry] | tuple[rc.RetrievalContextEntry, ...],
) -> rc.RetrievalContextProjection:
    user_payload: dict[str, Any] = {}
    receipts: list[dict[str, object]] = []
    refusal_receipts: list[dict[str, object]] = []

    for entry in entries:
        try:
            admission = rc._admit_entry(entry)  # type: ignore[attr-defined]
        except rc.RetrievalContextAdmissionError as exc:
            refusal_receipts.extend(dict(receipt) for receipt in exc.refusal_receipts)
            continue

        duplicate_fields = [
            source_field
            for source_field in admission.user_payload
            if source_field in user_payload
        ]
        if duplicate_fields:
            refusal_receipts.extend(
                rc._duplicate_projection_receipt(  # type: ignore[attr-defined]
                    receipt,
                    duplicate_fields=duplicate_fields,
                )
                for receipt in admission.untrusted_context_receipts
            )
            continue

        user_payload.update(dict(admission.user_payload))
        receipts.extend(dict(receipt) for receipt in admission.untrusted_context_receipts)

    return rc.RetrievalContextProjection(
        user_payload=user_payload,
        untrusted_context_receipts=receipts,
        refusal_receipts=refusal_receipts,
    )


def _baseline_project_retrieval_store_records(records: list[dict[str, Any]]) -> rc.RetrievalContextProjection:
    entries: list[rc.RetrievalContextEntry] = []
    refusal_receipts: list[dict[str, object]] = []

    for record in records:
        if not isinstance(record, Mapping):  # pragma: no cover - defensive baseline fallback
            refusal_receipts.append(
                rc._store_record_refusal(  # type: ignore[attr-defined]
                    source_field="record",
                    source_id="unknown-retrieved-document",
                    context_kind="retrieved_document",
                )
            )
            continue

        context_kind = record.get("context_kind")
        if context_kind not in ("retrieved_document", "retrieved_image"):  # pragma: no cover - defensive baseline fallback
            source_id = rc._store_record_source_id(record)  # type: ignore[attr-defined]
            refusal_context_kind = rc._store_record_refusal_context_kind(source_id)  # type: ignore[attr-defined]
            refusal_receipts.append(
                rc._store_record_refusal(  # type: ignore[attr-defined]
                    source_field="context_kind",
                    source_id=source_id,
                    context_kind=refusal_context_kind,
                )
            )
            continue

        entries.append(
            rc.RetrievalContextEntry(
                context_kind=context_kind,
                source_id=record.get("source_id"),
                payload=record.get("payload"),
                owner_scope_checked=record.get("owner_scope_checked"),
                segment_id=record.get("segment_id", ""),
                source_field=record.get("source_field", ""),
                reason=record.get("reason", ""),
                corrective_action=record.get("corrective_action", ""),
            )
        )

    projection = rc.project_retrieval_contexts(entries)
    return rc.RetrievalContextProjection(
        user_payload=projection.user_payload,
        untrusted_context_receipts=projection.untrusted_context_receipts,
        refusal_receipts=[
            *(dict(receipt) for receipt in refusal_receipts),
            *(dict(receipt) for receipt in projection.refusal_receipts),
        ],
    )


def _measure(func: Any, entries: list[rc.RetrievalContextEntry], iterations: int) -> float:
    start = time.perf_counter()
    projected_count = 0
    receipt_count = 0
    for _ in range(iterations):
        projection = func(entries)
        projected_count += len(projection.user_payload)
        receipt_count += projection.untrusted_context_receipt_count
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    expected = len(entries) * iterations
    if projected_count != expected or receipt_count != expected:
        raise AssertionError(
            f"projection drift: projected={projected_count} receipts={receipt_count} expected={expected}"
        )
    return elapsed_ms / iterations


def _measure_store(func: Any, records: list[dict[str, Any]], iterations: int) -> float:
    start = time.perf_counter()
    projected_count = 0
    receipt_count = 0
    for _ in range(iterations):
        projection = func(records)
        projected_count += len(projection.user_payload)
        receipt_count += projection.untrusted_context_receipt_count
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    expected = len(records) * iterations
    if projected_count != expected or receipt_count != expected:  # pragma: no cover - probe integrity guard
        raise AssertionError(
            f"store projection drift: projected={projected_count} receipts={receipt_count} expected={expected}"
        )
    return elapsed_ms / iterations


def _mean(values: list[float]) -> float:
    return float(statistics.fmean(values))


def main() -> int:
    entry_count = _entry_count()
    sample_count = _samples()
    iteration_count = _iterations()
    entries = _build_entries(entry_count)
    records = _build_store_records(entries)
    admissions = _build_admissions(entries)
    original_admit_entry = rc._admit_entry  # type: ignore[attr-defined]

    def fake_admit_entry(entry: rc.RetrievalContextEntry) -> PromptContextAdmission:
        return admissions[entry.source_id]

    rc._admit_entry = fake_admit_entry  # type: ignore[attr-defined]
    try:
        # Warm both variants once before sampling.
        _measure(_baseline_project_retrieval_contexts, entries, 1)
        _measure(rc.project_retrieval_contexts, entries, 1)
        _measure_store(_baseline_project_retrieval_store_records, records, 1)
        _measure_store(rc.project_retrieval_store_records, records, 1)
        baseline = [
            _measure(_baseline_project_retrieval_contexts, entries, iteration_count)
            for _ in range(sample_count)
        ]
        optimized = [
            _measure(rc.project_retrieval_contexts, entries, iteration_count)
            for _ in range(sample_count)
        ]
        store_baseline = [
            _measure_store(_baseline_project_retrieval_store_records, records, iteration_count)
            for _ in range(sample_count)
        ]
        store_optimized = [
            _measure_store(rc.project_retrieval_store_records, records, iteration_count)
            for _ in range(sample_count)
        ]
    finally:
        rc._admit_entry = original_admit_entry  # type: ignore[attr-defined]

    baseline_mean = _mean(baseline)
    optimized_mean = _mean(optimized)
    store_baseline_mean = _mean(store_baseline)
    store_optimized_mean = _mean(store_optimized)
    delta_ms = optimized_mean - baseline_mean
    store_delta_ms = store_optimized_mean - store_baseline_mean
    speedup = baseline_mean / optimized_mean if optimized_mean > 0.0 else 0.0
    store_speedup = store_baseline_mean / store_optimized_mean if store_optimized_mean > 0.0 else 0.0
    payload = {
        "baseline_elapsed_ms_mean": baseline_mean,
        "optimized_elapsed_ms_mean": optimized_mean,
        "delta_ms": delta_ms,
        "speedup": speedup,
        "store_baseline_elapsed_ms_mean": store_baseline_mean,
        "store_optimized_elapsed_ms_mean": store_optimized_mean,
        "store_delta_ms": store_delta_ms,
        "store_speedup": store_speedup,
        "entry_count": float(entry_count),
        "sample_count": float(sample_count),
        "iteration_count": float(iteration_count),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
