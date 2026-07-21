# Dataset Quality Completion Dict Fast Path

## Goal

Reduce Python overhead in `worker.productization.dataset_preparation._append_rows_output_lengths(...)` for the common dataset quality path where generated prompt/completion rows are plain `dict` objects with a direct `completion` field.

## Scope

- Python-only performance slice.
- Affected implementation: `services/mlx-worker-python/worker/productization/dataset_preparation.py`.
- Existing behavior is preserved for message rows, non-string completions, mixed rows, and dict subclasses.
- No dataset schema, output artifact, partitioning, quality score, or CLI behavior changes.

## Registered Probe

The affected path is already covered by the registered PR-scoped probe `dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries covering:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_versioning.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_quality_lengths_probe.py`

## Plan

1. Confirm the registered probe and run the baseline probe locally on Linux.
2. Add one exact-`dict` completion-row fast path that avoids the sentinel `get()` branch for plain prompt/completion rows.
3. Keep the existing generic loop for dict subclasses and message/mixed fallback rows.
4. Run the registered focused tests, changed-scope coverage, and local registered probe.
5. Accept only if the local registered probe shows a clear non-regressive direction and CI registered probe completes successfully.

## Metrics

Primary metrics are emitted by `scripts/dataset_quality_lengths_probe.py`:

- `elapsed_ms_mean`
- `elapsed_ms_min`
- `elapsed_ms_p95`
- row counts and output-length statistics as parity guards

The failed-partition metrics emitted by the same probe are informational for this slice because the implementation change only targets output-length aggregation.
