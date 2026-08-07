# Dataset quality local string type checks

## Scope

This Python-only performance slice is limited to output-length accounting in
`worker.productization.dataset_preparation._append_rows_output_lengths()`.

The previous dataset quality slice already binds `str` as `str_` for coercion in
this hot loop, but the exact-type checks still read the global `str` name. This
slice keeps completion rows, chat message rows, malformed messages,
non-string-content fallback, mean, p95, and failed-partition behavior unchanged
while using the existing local `str_` binding for exact string type checks.

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`. The probe
has focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_versioning.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_quality_lengths_probe.py`

## Plan

1. Reuse the existing local `str_` binding for all exact `type(...) is str`
   checks inside `_append_rows_output_lengths()`.
2. Preserve the existing generic fallback for malformed, non-list, non-dict, and
   non-string-content rows.
3. Run the registered focused tests, changed-scope coverage, and local registered
   probe on Linux before opening the PR.
4. Use GitHub Actions PR-scoped performance as the final registered probe and
   merge gate.

## Expected metrics

The registered probe should report a lower `elapsed_ms_mean` for the dataset
quality output-length workload. Failed-partition metrics are reported by the
same probe but should remain neutral because this slice does not alter
`_partition_failed_segments()`.

## Linux boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
behavior is changed.
