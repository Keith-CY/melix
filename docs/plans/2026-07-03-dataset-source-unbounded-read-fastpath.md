# Dataset source unbounded read fast path

This Python-only performance slice is limited to dataset ingest source text loading in `worker.productization.dataset_preparation._read_source_text()`.

## Scope

Most dataset source-record probe fixtures read many small local text files without an upload or per-source byte cap. The previous implementation used the bounded chunk loop for both capped and uncapped reads, allocating a chunk list and joining bytes even when no limit enforcement was needed.

This slice adds a no-cap fast path that performs one binary `read()` and decodes the result directly. The bounded path remains unchanged for `cap_bytes > 0`, so upload-cap and source-cap enforcement semantics are preserved.

No dataset schema, source discovery, source-kind classification, segmentation, PII masking, deduplication, or output artifact behavior changes in this slice.

## Registered probe

The affected path is covered by the registered PR-scoped probe `dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_source_records_probe.py`

The relevant metrics are `record_elapsed_ms_mean`, `record_elapsed_ms_min`, `record_elapsed_ms_p95`, plus the overall `elapsed_ms_*` source discovery metrics.

## Implementation plan

1. Add a focused regression guard proving uncapped source reads use a single binary `read()`.
2. Keep the existing bounded chunk loop for positive caps.
3. Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the final merge gate.

## Validation boundary

This is a Python-only slice and is locally verifiable on Linux. GitHub Actions remains the final registered PR-scoped performance validation and merge gate.
