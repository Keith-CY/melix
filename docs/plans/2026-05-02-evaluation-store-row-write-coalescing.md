# Evaluation store row write coalescing performance slice

## Goal

Reduce per-row write overhead in the Python evaluation store sample artifact path without changing the persisted JSONL or CSV payloads.

## Scope

This slice is limited to:

- `services/mlx-worker-python/worker/productization/evaluation_store.py`
- `services/mlx-worker-python/tests/test_evaluation_store.py`
- the registered PR-scoped probe coverage already defined for `evaluation-store-samples-csv-streaming`

## Registered probe

The affected path is covered by `evaluation-store-samples-csv-streaming` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and measures:

- `elapsed_ms_mean` for persisting 10,000 evaluation samples
- `peak_bytes_mean` during the same persist operation

## Implementation plan

1. Preserve streaming semantics and output bytes for JSONL and CSV sample artifacts.
2. Coalesce each row and newline into one `write()` call in `_write_jsonl()` and `_write_samples_csv()` so the store performs one write per row rather than two.
3. Bind hot-loop writer and CSV-field formatter callables once per function call to avoid repeated attribute lookups while preserving row formatting semantics.
4. Update focused unit assertions to prove payload parity and reduced write-call shape.
5. Validate with the registered focused test command, coverage command, and local registered probe before pushing.

## Success criteria

- Persisted artifact content remains byte-for-byte identical for the covered cases.
- Changed-scope coverage remains at least 95%.
- The registered `evaluation-store-samples-csv-streaming` probe shows a clear `elapsed_ms_mean` improvement or a non-regressive result with lower per-row write overhead.
