# Dataset quality two-message fast path

## Scope

This Python-only performance slice is limited to output-length accounting in
`worker.productization.dataset_preparation._append_rows_output_lengths()`.

The registered dataset quality probe uses chat-style validation rows with two
exact-dict messages. The existing fallback loop handles that shape correctly but
still pays per-message loop and branch overhead. This slice keeps completion-row,
mixed-message, non-string-content, malformed-message, ordering, p95, and mean
semantics unchanged while adding a narrow fast path for the common two exact-dict
message shape where both `content` values are strings.

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

1. Preserve the existing generic message fallback for malformed, non-list,
   non-dict, and non-string-content rows.
2. Add a two-message exact-dict fast path for string `content` values.
3. Add a focused regression test covering the fast-path shape and fallback for a
   two-message row with non-string content.
4. Run focused tests, changed-scope coverage, and the registered local probe on
   Linux before opening the PR.
5. Use GitHub Actions PR-scoped performance as the final registered probe and
   merge gate.

## Expected metrics

The registered probe should report a lower `elapsed_ms_mean` for the dataset
quality output-length workload. Failed-partition metrics are reported by the
same probe but should remain neutral because this slice does not alter
`_partition_failed_segments()`.
