# Statistical Category Breakdown Deferred Correctness Counts

## Goal

Reduce per-row category aggregation overhead in `build_category_breakdown(...)` by deferring `base_correct` and `target_correct` integer conversion until after the category label is known to be non-empty and an existing totals row is selected. The slice preserves category label stripping, empty-label skipping, truthiness handling for correctness fields, sorted output keys, and rounded payload fields.

## Scope

- `services/mlx-worker-python/worker/productization/statistical_evidence.py`
- Existing focused tests in `services/mlx-worker-python/tests/test_statistical_evidence.py`
- Registered probe `statistical-evidence-category-breakdown-single-pass`

## Registered Probe

The affected path is covered by `statistical-evidence-category-breakdown-single-pass` in `infra/perf/pr_scoped_probes.json`. The registered probe already has focused `test_command`, `coverage_command`, and `probe_command` entries and reports `elapsed_ms_mean`, `peak_bytes_mean`, row count, category count, sample count, and checksum.

## Verification Plan

1. Run the registered focused pytest command for `statistical-evidence-category-breakdown-single-pass`.
2. Run the registered changed-scope coverage command and require at least 95% for touched executable scope.
3. Run the registered category-breakdown probe locally on Linux before and after the change and compare repeated samples.
4. Run `git diff --check` before committing.

## Success Metrics

- Preserve checksum, row count, category count, sample count, and focused test behavior.
- Improve or hold steady `elapsed_ms_mean` in repeated local Linux probe samples.
- Keep `peak_bytes_mean` unchanged, since the aggregate and output data structures are intentionally unchanged.
