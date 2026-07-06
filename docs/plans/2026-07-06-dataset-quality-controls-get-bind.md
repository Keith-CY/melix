# Dataset quality controls get binding performance slice

This Python-only performance slice is limited to `worker.productization.dataset_preparation._quality_summary`.

## Scope

`_quality_summary` repeatedly reads values from the `quality_control_summary` mapping while building dataset version quality output. The slice keeps the output schema and quality scoring behavior unchanged while binding `quality_controls.get` once and reusing it for the source record, deduplication, and PII-mask fields.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe `dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`. That registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries. The probe exercises `_quality_summary` over synthetic train and validation rows and also keeps the failed-segment partition metric in the same dataset-preparation hot-path report.

## Validation plan

This slice is Python-only and locally verifiable on Linux:

1. Run the focused dataset preparation tests from the registered probe.
2. Run changed-scope coverage over `dataset_preparation.py`, the dataset preparation tests, PR-scoped performance tests, and `scripts/dataset_quality_lengths_probe.py`.
3. Run the registered `dataset-quality-lengths-chain` probe locally against `origin/main` and the branch with `scripts/pr_scoped_performance_run.py`.
4. Use GitHub Actions PR-scoped performance as the merge gate after opening the PR.

No Swift runtime behavior is changed.
