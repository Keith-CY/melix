# Dataset preview limit-one JSON fast path

## Scope

This slice keeps the registered `dataset-registry-preview-limit-short-circuit`
probe focused on `worker/dataset_registry/catalog.py` and narrows the JSON
preview hot path used by `read_hf_dataset_snapshot_rows(..., limit=1)`.

## Change

- Avoid rebuilding the first preview chunk with `"".join(chunks)` before parsing.
- Return immediately when the limited JSON preview parser decodes the first dict
  and the requested limit is exactly one.

The behavior stays unchanged for empty files, multi-row limits, non-dict array
entries, and fallback full JSON loading.

## Verification

Run the registered probe locally on Linux before opening the PR, then rely on the
PR-scoped performance workflow for CI validation. The expected signal is lower
`elapsed_ms_mean` and a small reduction in `peak_bytes_mean` for the registered
`dataset-registry-preview-limit-short-circuit` probe.

## Follow-up Slice: First-File Helper Local Bindings

The 2026-07-26 follow-up keeps the same registered probe and narrows to
`_next_supported_scan_entry()` in the `limit=1` preview path. The first-file scan
now binds the README-name set, supported-suffix helper, and `Path` constructor as
locals for the loop, preserving existing OSError and recursive directory
semantics while reducing global lookups in the synthetic first-preview workload.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass with lower elapsed time, and if the PR-scoped CI
probe completes successfully before merge.

## Follow-up Slice: Multi-Limit Late Path Construction

The 2026-08-01 follow-up keeps the same registered probe and narrows to the
multi-file preview iterator used when `read_hf_dataset_snapshot_rows(...,
limit=N)` has no split filter and `N > 1`. The iterator now asks the bounded
scan helper for raw path strings and constructs `Path` objects only when a
selected entry is actually processed. This preserves sorted depth-first preview
semantics while avoiding `Path` allocation for selected sibling candidates that
become unnecessary after an earlier directory yields enough rows.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass, and if the PR-scoped CI probe reports no regression
before merge.
