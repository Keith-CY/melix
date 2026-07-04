# Dataset quality completion get fast path

This Python-only performance slice is limited to output-length collection in `worker.productization.dataset_preparation._append_rows_output_lengths()`.

## Scope

The registered dataset quality workload contains a large train split where rows usually expose `completion` directly, plus a validation split with `messages`. The current hot loop uses exception-driven `row["completion"]` lookup for every message-style row. This slice keeps the same ordering and fallback semantics while making the direct completion path explicit and avoiding `KeyError` construction on message rows.

No dataset schema, partitioning, quality score, package manifest, row ordering, or output artifact behavior changes in this slice.

## Registered probe

The affected path is covered by the registered PR-scoped probe `dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_versioning.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_quality_lengths_probe.py`

The primary local metric is `elapsed_ms_mean`; failed-partition metrics are expected to remain neutral because this slice does not touch that path.

## Implementation plan

1. Run the registered probe on the synced baseline to record local Linux performance.
2. Add a regression guard proving message-style rows do not rely on exception-driven completion lookup.
3. Implement one focused hot-loop change in `_append_rows_output_lengths()`.
4. Run the focused test command, changed-scope coverage command, and registered probe locally on Linux.
5. Use GitHub Actions PR-scoped performance as the final merge gate.

## Validation boundary

This is a Python-only slice and is locally verifiable on Linux. GitHub Actions remains the final registered PR-scoped performance validation and merge gate.
