# LoRA Run Directory Entry Name Binding

## Linux-only constraint

This slice is Python-only and locally verifiable on Linux with focused pytest,
changed-scope coverage, and the registered PR-scoped performance probe.

## Optimization

`lora_experiment_store._iter_lora_run_dirs()` scans `train_lora` entries,
filters `model-ops-` directories, sorts by run directory name, and rebuilds
`Path` values from the sorted names.

This slice keeps that behavior unchanged while reading `DirEntry.name` once per
entry and reusing the local `entry_name` for both the prefix check and append.
It also binds the static run-directory prefix outside the scan loop. This
reduces repeated attribute and constant lookup overhead on the hot scan path
without reading `DirEntry.path` or changing sort semantics.

## Registered probe

Existing registered probe: `lora-experiment-run-dir-name-scan` in
`infra/perf/pr_scoped_probes.json`.

The probe covers:

- `services/mlx-worker-python/worker/productization/lora_experiment_store.py`
- `services/mlx-worker-python/tests/test_lora_experiment_store.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/lora_experiment_run_dir_scan_probe.py`

The registry defines focused `test_command`, `coverage_command`, and
`probe_command` entries for this path. This slice also keeps the probe command
anchored to `scripts/lora_experiment_run_dir_scan_probe.py` and adds the
`name_attr_reads_mean` metric so the PR-scoped report can validate the reduced
entry-name access count directly.

## Verification plan

Run the registered focused tests, changed-scope coverage, and local registered
probe on Linux before opening the PR. The PR-scoped performance workflow remains
the merge gate for the registered probe result in CI.
