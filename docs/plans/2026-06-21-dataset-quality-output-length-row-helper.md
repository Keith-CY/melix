# Dataset Quality Output Length Row Helper

This Python-only performance slice is limited to `worker.productization.dataset_preparation._append_sample_output_lengths()`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`. The probe entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the dataset quality output-length path.

## Change

`_append_sample_output_lengths()` previously iterated over a temporary `(train_rows, validation_rows)` tuple and kept the per-row extraction loop nested under that outer loop. This slice keeps output semantics unchanged while moving the row loop into `_append_rows_output_lengths()` and calling it once for train rows and once for validation rows. The goal is to remove the outer tuple iteration from the hot path and keep local `append`/`str` bindings scoped to the direct row pass.

## Verification Plan

1. Run the registered local probe on `origin/main` before the change and on `HEAD` after the change.
2. Run the registered focused tests for `dataset-quality-lengths-chain`.
3. Run the registered changed-scope coverage command and confirm at least 95% coverage for the touched scope.
4. Run `git diff --check`.
5. Use GitHub Actions and the registered PR-scoped performance report as the merge gate.

## Validation Boundary

Linux-local Python behavior and probe metrics are valid for this slice. No Swift runtime effect is claimed.
