#!/usr/bin/env python3
from __future__ import annotations

import copy
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


def _build_lookup_payload(count: int) -> dict[str, Any]:
    return {
        f"retrieved_context_{index}": {
            "index": index,
            "title": f"retrieved payload {index}",
            "metadata": {
                "optional_note": None,
                "scores": [
                    index,
                    index + 1,
                    {"rank": index % 7},
                    {"score": (index % 13) / 13},
                    {"shard": index % 11},
                ],
                "six_scores": [
                    index,
                    index + 1,
                    {"rank": index % 7},
                    {"score": (index % 13) / 13},
                    {"shard": index % 11},
                    {"page": index % 17},
                ],
                "seven_scores": [
                    index,
                    index + 1,
                    {"rank": index % 7},
                    {"score": (index % 13) / 13},
                    {"shard": index % 11},
                    {"page": index % 17},
                    {"section": index % 19},
                ],
                "eight_scores": [
                    index,
                    index + 1,
                    {"rank": index % 7},
                    {"score": (index % 13) / 13},
                    {"shard": index % 11},
                    {"page": index % 17},
                    {"section": index % 19},
                    {"chunk": index % 23},
                ],
                "nine_scores": [
                    index,
                    index + 1,
                    {"rank": index % 7},
                    {"score": (index % 13) / 13},
                    {"shard": index % 11},
                    {"page": index % 17},
                    {"section": index % 19},
                    {"chunk": index % 23},
                    {"offset": index % 29},
                ],
                "six_score_window": [
                    {"first": index},
                    {"second": index + 1},
                    {"rank": index % 7},
                    {"score": (index % 13) / 13},
                    {"shard": index % 11},
                    {"page": index % 17},
                ],
                "quad_scores": [
                    index,
                    index + 1,
                    {"rank": index % 7},
                    {"score": (index % 13) / 13},
                ],
                "single_key_detail": {"summary": {"nested": index % 23}},
                "labels": (
                    "retrieved",
                    {"kind": "document" if index % 2 == 0 else "image"},
                    {"bucket": index % 3},
                    {"source": index % 5},
                    {"shard": index % 11},
                ),
                "six_labels": (
                    "retrieved",
                    {"kind": "document" if index % 2 == 0 else "image"},
                    {"bucket": index % 3},
                    {"source": index % 5},
                    {"shard": index % 11},
                    {"page": index % 17},
                ),
                "seven_labels": (
                    "retrieved",
                    {"kind": "document" if index % 2 == 0 else "image"},
                    {"bucket": index % 3},
                    {"source": index % 5},
                    {"shard": index % 11},
                    {"page": index % 17},
                    {"section": index % 19},
                ),
                "eight_labels": (
                    "retrieved",
                    {"kind": "document" if index % 2 == 0 else "image"},
                    {"bucket": index % 3},
                    {"source": index % 5},
                    {"shard": index % 11},
                    {"page": index % 17},
                    {"section": index % 19},
                    {"chunk": index % 23},
                ),
                "nine_labels": (
                    "retrieved",
                    {"kind": "document" if index % 2 == 0 else "image"},
                    {"bucket": index % 3},
                    {"source": index % 5},
                    {"shard": index % 11},
                    {"page": index % 17},
                    {"section": index % 19},
                    {"chunk": index % 23},
                    {"offset": index % 29},
                ),
                "six_label_window": (
                    {"role": "retrieved"},
                    {"kind": "document" if index % 2 == 0 else "image"},
                    {"bucket": index % 3},
                    {"source": index % 5},
                    {"shard": index % 11},
                    {"page": index % 17},
                ),
            },
        }
        for index in range(count)
    }


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


def _baseline_copy_lookup_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(payload))


def _measure_lookup_copy(func: Any, payload: Mapping[str, Any], iterations: int) -> float:
    start = time.perf_counter()
    projected_count = 0
    checksum = 0
    for _ in range(iterations):
        copied = func(payload)
        projected_count += len(copied)
        checksum += copied["retrieved_context_0"]["metadata"]["scores"][2]["rank"]
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    if projected_count != len(payload) * iterations or checksum != 0:
        raise AssertionError(
            f"lookup payload copy drift: projected={projected_count} checksum={checksum}"
        )
    return elapsed_ms / iterations


class _CountingLookupResult(dict[str, Any]):
    def __init__(self) -> None:
        super().__init__({"records": None})
        self.get_calls = 0

    def get(self, key: str, default: Any = None) -> Any:
        if key == "records":
            self.get_calls += 1
        return super().get(key, default)


def _baseline_lookup_adapter(
    lookup_result: Mapping[str, Any],
    *,
    lookup_source_id: Any = "",
    lookup_segment_id: Any = "",
    lookup_source_field: Any = "",
) -> rc.RetrievalLookupResultProjection:
    wrapper_metadata_refusal = rc._lookup_result_metadata_refusal(  # type: ignore[attr-defined]
        lookup_source_id=lookup_source_id,
        lookup_segment_id=lookup_segment_id,
        lookup_source_field=lookup_source_field,
    )
    if wrapper_metadata_refusal is not None:  # pragma: no cover - defensive baseline parity
        return rc.RetrievalLookupResultProjection(
            prompt_user_payload={},
            untrusted_context_receipts=[],
            refusal_receipts=[wrapper_metadata_refusal],
            lookup_message=None,
        )
    normalized_lookup_source_id = rc._lookup_metadata_text_or_default(  # type: ignore[attr-defined]
        lookup_source_id,
        default="unknown-retrieval-lookup",
    )
    normalized_lookup_segment_id = rc._lookup_metadata_text_or_default(  # type: ignore[attr-defined]
        lookup_segment_id,
        default=f"{normalized_lookup_source_id}:lookup-result",
    )
    normalized_lookup_source_field = rc._lookup_metadata_text_or_default(  # type: ignore[attr-defined]
        lookup_source_field,
        default="lookup_result",
    )
    has_lookup_metadata = (
        lookup_source_id != "" or lookup_segment_id != "" or lookup_source_field != ""
    )
    store_projection = rc.project_retrieval_store_records(lookup_result.get("records"))
    prompt_user_payload = rc._copy_payload(store_projection.user_payload)  # type: ignore[attr-defined]
    untrusted_context_receipts = rc._copy_receipts(store_projection.untrusted_context_receipts)  # type: ignore[attr-defined]
    refusal_receipts = rc._copy_receipts(store_projection.refusal_receipts)  # type: ignore[attr-defined]
    if (
        has_lookup_metadata
        and (
            "records" not in lookup_result
            or not isinstance(lookup_result.get("records"), list)
        )
        and len(refusal_receipts) == 1
        and not prompt_user_payload
        and not untrusted_context_receipts
    ):
        refusal_receipts = [
            rc._lookup_result_refusal(  # type: ignore[attr-defined]
                source_id=normalized_lookup_source_id,
                segment_id=normalized_lookup_segment_id,
                source_field=normalized_lookup_source_field,
            )
        ]
    lookup_message = None
    if prompt_user_payload:  # pragma: no cover - defensive baseline parity
        lookup_message = {
            "role": "user",
            "content": prompt_user_payload,
            "untrusted_context_receipts": untrusted_context_receipts,
        }
    return rc.RetrievalLookupResultProjection(
        prompt_user_payload=prompt_user_payload,
        untrusted_context_receipts=untrusted_context_receipts,
        refusal_receipts=refusal_receipts,
        lookup_message=lookup_message,
    )


def _measure_lookup_records_gets(func: Any, iterations: int) -> tuple[float, float]:
    start = time.perf_counter()
    get_calls = 0
    refusal_count = 0
    for _ in range(iterations):
        lookup_result = _CountingLookupResult()
        projection = func(
            lookup_result,
            lookup_source_id="probe-lookup",
            lookup_segment_id="probe-lookup:lookup-result",
            lookup_source_field="probe_lookup_records",
        )
        get_calls += lookup_result.get_calls
        refusal_count += len(projection.refusal_receipts)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    if refusal_count != iterations:  # pragma: no cover - probe integrity guard
        raise AssertionError(f"lookup records refusal drift: {refusal_count} != {iterations}")
    return elapsed_ms / iterations, get_calls / iterations


def _mean(values: list[float]) -> float:
    return float(statistics.fmean(values))


def main() -> int:
    entry_count = _entry_count()
    sample_count = _samples()
    iteration_count = _iterations()
    entries = _build_entries(entry_count)
    records = _build_store_records(entries)
    lookup_payload = _build_lookup_payload(entry_count)
    admissions = _build_admissions(entries)
    original_admit_entry = rc._admit_entry  # type: ignore[attr-defined]

    def fake_admit_entry(entry: rc.RetrievalContextEntry) -> PromptContextAdmission:
        return admissions[entry.source_id]

    # Measure direct entry projection with the real admission path so complete
    # RetrievalContextEntry optimizations are not hidden by the store/lookup
    # prebuilt-admission isolation shim below.
    _measure(_baseline_project_retrieval_contexts, entries, 1)
    _measure(rc.project_retrieval_contexts, entries, 1)
    baseline = [
        _measure(_baseline_project_retrieval_contexts, entries, iteration_count)
        for _ in range(sample_count)
    ]
    optimized = [
        _measure(rc.project_retrieval_contexts, entries, iteration_count)
        for _ in range(sample_count)
    ]

    rc._admit_entry = fake_admit_entry  # type: ignore[attr-defined]
    try:
        # Warm store/lookup variants once before sampling.
        _measure_store(_baseline_project_retrieval_store_records, records, 1)
        _measure_store(rc.project_retrieval_store_records, records, 1)
        _measure_lookup_copy(_baseline_copy_lookup_payload, lookup_payload, 1)
        _measure_lookup_copy(rc._copy_payload, lookup_payload, 1)  # type: ignore[attr-defined]
        _measure_lookup_records_gets(_baseline_lookup_adapter, 1)
        _measure_lookup_records_gets(rc.project_retrieval_lookup_result, 1)
        store_baseline = [
            _measure_store(_baseline_project_retrieval_store_records, records, iteration_count)
            for _ in range(sample_count)
        ]
        store_optimized = [
            _measure_store(rc.project_retrieval_store_records, records, iteration_count)
            for _ in range(sample_count)
        ]
        lookup_copy_baseline = [
            _measure_lookup_copy(_baseline_copy_lookup_payload, lookup_payload, iteration_count)
            for _ in range(sample_count)
        ]
        lookup_copy_optimized = [
            _measure_lookup_copy(rc._copy_payload, lookup_payload, iteration_count)  # type: ignore[attr-defined]
            for _ in range(sample_count)
        ]
        lookup_records_baseline = [
            _measure_lookup_records_gets(_baseline_lookup_adapter, iteration_count)
            for _ in range(sample_count)
        ]
        lookup_records_optimized = [
            _measure_lookup_records_gets(rc.project_retrieval_lookup_result, iteration_count)
            for _ in range(sample_count)
        ]
    finally:
        rc._admit_entry = original_admit_entry  # type: ignore[attr-defined]

    baseline_mean = _mean(baseline)
    optimized_mean = _mean(optimized)
    store_baseline_mean = _mean(store_baseline)
    store_optimized_mean = _mean(store_optimized)
    lookup_copy_baseline_mean = _mean(lookup_copy_baseline)
    lookup_copy_optimized_mean = _mean(lookup_copy_optimized)
    lookup_records_baseline_elapsed_mean = _mean([sample[0] for sample in lookup_records_baseline])
    lookup_records_optimized_elapsed_mean = _mean([sample[0] for sample in lookup_records_optimized])
    lookup_records_baseline_gets_mean = _mean([sample[1] for sample in lookup_records_baseline])
    lookup_records_optimized_gets_mean = _mean([sample[1] for sample in lookup_records_optimized])
    delta_ms = optimized_mean - baseline_mean
    store_delta_ms = store_optimized_mean - store_baseline_mean
    lookup_copy_delta_ms = lookup_copy_optimized_mean - lookup_copy_baseline_mean
    lookup_records_delta_ms = lookup_records_optimized_elapsed_mean - lookup_records_baseline_elapsed_mean
    speedup = baseline_mean / optimized_mean if optimized_mean > 0.0 else 0.0
    store_speedup = store_baseline_mean / store_optimized_mean if store_optimized_mean > 0.0 else 0.0
    lookup_copy_speedup = (
        lookup_copy_baseline_mean / lookup_copy_optimized_mean
        if lookup_copy_optimized_mean > 0.0
        else 0.0
    )
    payload = {
        "baseline_elapsed_ms_mean": baseline_mean,
        "optimized_elapsed_ms_mean": optimized_mean,
        "delta_ms": delta_ms,
        "speedup": speedup,
        "store_baseline_elapsed_ms_mean": store_baseline_mean,
        "store_optimized_elapsed_ms_mean": store_optimized_mean,
        "store_delta_ms": store_delta_ms,
        "store_speedup": store_speedup,
        "lookup_copy_baseline_elapsed_ms_mean": lookup_copy_baseline_mean,
        "lookup_copy_optimized_elapsed_ms_mean": lookup_copy_optimized_mean,
        "lookup_copy_delta_ms": lookup_copy_delta_ms,
        "lookup_copy_speedup": lookup_copy_speedup,
        "lookup_records_baseline_elapsed_ms_mean": lookup_records_baseline_elapsed_mean,
        "lookup_records_optimized_elapsed_ms_mean": lookup_records_optimized_elapsed_mean,
        "lookup_records_delta_ms": lookup_records_delta_ms,
        "lookup_records_baseline_get_calls_mean": lookup_records_baseline_gets_mean,
        "lookup_records_optimized_get_calls_mean": lookup_records_optimized_gets_mean,
        "entry_count": float(entry_count),
        "sample_count": float(sample_count),
        "iteration_count": float(iteration_count),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
