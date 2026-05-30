# LoRA Experiment Run Directory Path Map

## Linux-only constraint

This slice is Python-only and locally verifiable on Linux with focused pytest,
changed-scope coverage, and the registered PR-scoped performance probe.

## Optimization

`lora_experiment_store._iter_lora_run_dirs()` scans LoRA training run
directories and filters `model-ops-` entries before sorting names. The function
then rebuilds `Path` values from the sorted names.

This slice keeps the scan and sorting semantics unchanged while using
`tuple(map(root_join, run_dir_names))` for the final sorted-name-to-`Path`
conversion. That avoids the generator frame used by the previous tuple
comprehension and slightly reduces allocation overhead in the registered scan
probe.

## Registered probe

Existing registered probe: `lora-experiment-run-dir-name-scan` in
`infra/perf/pr_scoped_probes.json`.

The probe covers:

- `services/mlx-worker-python/worker/productization/lora_experiment_store.py`
- `services/mlx-worker-python/tests/test_lora_experiment_store.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/lora_experiment_run_dir_scan_probe.py`

The registry already defines focused `test_command`, `coverage_command`, and
`probe_command` entries, so no probe registry change is needed for this narrow
prefix-binding optimization.

## Verification plan

Run the registered focused tests, changed-scope coverage, and local registered
probe on Linux before opening the PR. The PR-scoped performance workflow remains
the merge gate for the registered probe result in CI.
