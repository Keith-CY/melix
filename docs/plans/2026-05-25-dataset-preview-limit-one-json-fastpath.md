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
