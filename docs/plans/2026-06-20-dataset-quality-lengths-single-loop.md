# Dataset Quality Output Length Single-Loop Slice

## Scope

This Python-only performance slice is limited to dataset quality output length collection in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.

The implementation keeps dataset quality summary semantics unchanged while avoiding duplicated train/validation loop bodies in `_append_sample_output_lengths(...)`. The helper now iterates the two row collections through one shared hot loop, preserving train rows before validation rows and all existing completion/message fallback behavior.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_versioning.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_quality_lengths_probe.py`

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and registered local probe on Linux before pushing. GitHub Actions PR-scoped performance remains the final registered probe validation and merge gate.

## Metrics

Use `scripts/dataset_quality_lengths_probe.py` with the registered default dataset (`12,000` train rows, `3,000` validation rows, seven samples) and a higher-sample local comparison when needed. Primary metrics are `elapsed_ms_mean`, `elapsed_ms_min`, and `elapsed_ms_p95`; output length statistics remain informational parity checks.
