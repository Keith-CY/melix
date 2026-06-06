# Dataset Quality Count Cache Slice

## Scope

This Python-only performance slice is limited to `worker.productization.dataset_preparation._quality_summary`.
The quality summary already scans generated rows for output-length statistics; this slice avoids redundant `len()` calls for train and validation row collections after the counts are computed for `success_count`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values and runs `scripts/dataset_quality_lengths_probe.py`.

## Plan

1. Add a focused regression test proving train and validation counts are reused while preserving generated sample count semantics.
2. Cache `train_count` and `validation_count` inside `_quality_summary` and reuse those values in the returned payload.
3. Verify with the registered focused test command, changed-scope coverage command, and registered local Linux probe before pushing.
4. Use PR-scoped performance CI as the merge gate.

## Metrics

Success is measured by `elapsed_ms_mean` from `scripts/dataset_quality_lengths_probe.py` with unchanged `mean_output_length`, `p95_output_length`, and row counts. Changed-scope coverage must stay at or above 95%.
