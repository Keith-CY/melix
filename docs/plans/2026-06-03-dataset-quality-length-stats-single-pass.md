# Dataset quality length stats single-pass slice

## Scope

This Python-only performance slice is limited to dataset quality output length aggregation in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.

The existing behavior remains unchanged: quality summaries still report mean and p95 output length for both prompt/completion rows and chat-message rows.

## Registered probe

The affected path is covered by the registered PR-scoped probe `dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_versioning.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_quality_lengths_probe.py`

## Implementation plan

1. Keep `_sample_output_lengths()` as the semantic helper used by tests.
2. Add an internal stats helper for `_quality_summary()` that collects output lengths once, computes count and total, then sorts the same list in place for p95.
3. Avoid the previous second pass for `sum(lengths)` plus the extra `sorted(values)` allocation in `_p95()` on the quality-summary hot path.
4. Verify with focused pytest, changed-scope coverage, and the registered local probe on Linux before opening the PR.
5. Use PR-scoped performance CI as the merge gate.

## Success criteria

- Focused dataset quality tests pass.
- Changed-scope coverage for touched executable Python scope is at least 95%.
- Local registered probe shows a lower `elapsed_ms_mean` for the dataset quality length workload.
- CI selects and completes the registered PR-scoped probe successfully.
