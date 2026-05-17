# Dataset Preview JSON Streaming Slice

## Scope

This Python-only performance slice is limited to the dataset registry preview path in
`services/mlx-worker-python/worker/dataset_registry/catalog.py` when callers request a
small `limit` from a JSON snapshot file.

## Root cause and hypothesis

`read_hf_dataset_snapshot_rows(..., limit=1)` already short-circuits file selection and
uses `_limited_rows_from_json_text(...)` to avoid full `json.loads(...)` payload decode.
However, `_read_rows_from_file(...)` still calls `Path.read_text(...)` before the
limited parser, so a large canonical `{"rows": [...]}` preview pays the full file read
and string allocation cost even when the first row is enough.

Hypothesis: read bounded chunks for limited JSON previews and run the existing limited
JSON parser against the growing prefix. If enough rows are decoded before EOF, return
without materializing the full file text; otherwise fall back to the existing full-file
behavior for parity.

## Registered performance probe

The affected path is covered by the existing PR-scoped probe
`dataset-registry-preview-limit-short-circuit` in `infra/perf/pr_scoped_probes.json`.
It has focused `test_command`, `coverage_command`, and `probe_command` entries and
reports `elapsed_ms_mean` plus `peak_bytes_mean` for a synthetic large JSON preview.

## Verification plan

- Run the focused pytest command registered for `dataset-registry-preview-limit-short-circuit`.
- Run the registered coverage command and enforce changed-scope coverage.
- Run the registered probe locally on Linux before and after this slice.
- Use PR-scoped performance CI as the merge gate for base-vs-head validation.

## Success criteria

- Behavior remains identical for supported JSON/JSONL/CSV/Parquet/Arrow preview tests.
- Limited canonical JSON preview no longer requires `Path.read_text(...)`.
- For wrapper objects whose first key is `rows` or `data`, the limited parser should find
  the preview array without an extra `JSONDecoder.raw_decode(...)` call for the key.
- The local registered probe shows lower mean elapsed time and/or peak bytes without
  changing returned rows.
