# Dataset Quality Output Length Row Helper

This Python-only performance slice is limited to `worker.productization.dataset_preparation._append_sample_output_lengths()`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`. The probe entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the dataset quality output-length path.

## Change

`_append_sample_output_lengths()` previously iterated over a temporary `(train_rows, validation_rows)` tuple and kept the per-row extraction loop nested under that outer loop. This slice keeps output semantics unchanged while moving the row loop into `_append_rows_output_lengths()` and calling it once for train rows and once for validation rows. The goal is to remove the outer tuple iteration from the hot path and keep local `append`/`str` bindings scoped to the direct row pass.

A 2026-07-06 follow-up keeps the same row helper and returns the accumulated output-length total while appending each length. `_sample_output_length_stats()` uses that inline total instead of rescanning the collected lengths with `sum()` before sorting for p95, preserving output semantics while removing one full pass over the hot length list. The registered probe default sample count also increases from 7 to 25 so the short dataset-quality timing path is less sensitive to single-sample scheduler noise in CI and local comparisons.

A 2026-07-11 follow-up keeps the same row helper but checks key presence before reading prompt-completion rows. The synthetic registered probe is dominated by prompt-completion train rows, so the helper avoids `dict.get()` plus sentinel comparison on that common path while preserving the existing message-row behavior and p95/mean output-length semantics.

## Verification Plan

1. Run the registered local probe on `origin/main` before the change and on `HEAD` after the change.
2. Run the registered focused tests for `dataset-quality-lengths-chain`.
3. Run the registered changed-scope coverage command and confirm at least 95% coverage for the touched scope.
4. Run `git diff --check`.
5. Use GitHub Actions and the registered PR-scoped performance report as the merge gate.

## Validation Boundary

Linux-local Python behavior and probe metrics are valid for this slice. No Swift runtime effect is claimed.
