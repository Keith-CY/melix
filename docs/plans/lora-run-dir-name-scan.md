# LoRA run-dir name scan optimization

## Goal

Reduce temporary object retention in the LoRA experiment index rebuild path by keeping only eligible run-directory names while scanning `train_lora/`, instead of retaining `os.DirEntry` objects until after sorting.

## Linux-only constraint

This is a Python worker slice. It is locally verifiable on Linux with focused pytest, changed-scope coverage, and a synthetic probe. No Swift/macOS local validation is required.

## Touched files

- `services/mlx-worker-python/worker/productization/lora_experiment_store.py`
- `services/mlx-worker-python/tests/test_lora_experiment_store.py`
- `scripts/lora_experiment_run_dir_scan_probe.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Probe

Register `lora-experiment-run-dir-name-scan` in the PR-scoped performance registry.

The probe monkeypatches `os.scandir()` with many fake `DirEntry`-like objects and measures repeated `_iter_lora_run_dirs(...)` calls. It reports:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `run_dir_count`
- `path_attr_reads_mean`

## Success metrics

- Preserve sorted path output and unreadable-entry fallback behavior.
- Drive `path_attr_reads_mean` to `0.0` on the optimized branch while `origin/main` reads `entry.path` once per eligible run directory.
- Reduce `peak_bytes_mean` for the synthetic scan workload.
- Keep `elapsed_ms_mean` in the probe output as informational because this slice prioritizes lower retention/metadata access over latency.
- Keep changed-scope coverage at or above 95%.
