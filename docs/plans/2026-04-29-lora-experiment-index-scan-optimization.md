# LoRA Experiment Index Scan Optimization Plan

## Scope
- Repository: `services/mlx-worker-python`
- Touched executable path: `worker/productization/lora_experiment_store.py`
- Touched tests: `tests/test_lora_experiment_store.py`
- Linux-only constraint: only Python code and pytest-verifiable behavior; no Swift/macOS validation.

## Goal
Reduce redundant filesystem scans and repeated JSON parsing during LoRA experiment index rebuilds by scanning each run directory once instead of globbing run records and manifests in separate passes.

## Current Issue
`LoraExperimentStore.rebuild_index()` currently walks `train_lora/model-ops-*` twice: once for `lora-experiment-run.json` and once for `train_lora.adapter.json`. When both files exist in the same run directory, the second pass still reparses many manifests even though the run record already wins for that run.

## Proposed Change
- Iterate the sorted `train_lora/model-ops-*` directories once.
- Prefer an existing run record for each run directory.
- Fall back to `train_lora.adapter.json` only when the run record is missing, unreadable, or lacks a usable `run_id`.
- Preserve index ordering and payload shape.

## Test Plan
1. Add focused regression tests for run-record precedence and manifest fallback behavior.
2. Run targeted pytest for `tests/test_lora_experiment_store.py`.
3. Implement the minimal index rebuild change.
4. Re-run targeted pytest.
5. Run changed-scope coverage and require at least 95% automated coverage for `worker/productization/lora_experiment_store.py`.

## Performance Probe
Build a synthetic `train_lora/` tree with many run directories containing both a run record and a manifest, then compare a baseline double-scan implementation against the optimized one.

### Measurement
- wall-clock elapsed seconds across repeated rebuild runs
- synthetic repo shape: hundreds of `model-ops-*` run directories with both files present
- payload equivalence for discovered run IDs and ordering

### Success Metric
- identical index run IDs before and after
- measurable reduction in elapsed time for repeated synthetic rebuilds

## Verification Commands
- `PYTHONPATH=<repo>:<repo>/services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_experiment_store.py`
- `PYTHONPATH=<repo>:<repo>/services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_lora_experiment_store.py`
- `coverage report -m services/mlx-worker-python/worker/productization/lora_experiment_store.py services/mlx-worker-python/tests/test_lora_experiment_store.py`
- `git diff --check`
