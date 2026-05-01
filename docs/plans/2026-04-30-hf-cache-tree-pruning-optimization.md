# Hugging Face Cache Tree Pruning Optimization

## Goal

Avoid redundant generic registry-tree traversal work for Hugging Face cache roots in `services/mlx-worker-python/worker/model_registry/catalog.py` while preserving current model discovery behavior.

## Linux-Only Constraint

This optimization is limited to the Python worker codepath and must be fully verifiable on Linux with targeted pytest, coverage, and a synthetic filesystem-scan performance probe.

## Touched Files

- `services/mlx-worker-python/worker/model_registry/catalog.py`
- `services/mlx-worker-python/tests/test_model_registry_catalog.py`

## Planned Change

- Teach the generic registry root walker to prune Hugging Face cache-specific subtrees (`models--*`, `snapshots`, `refs`) instead of feeding those directories into the plain local model directory scan.
- Preserve dedicated Hugging Face cache discovery via `_scan_huggingface_cache_models()`.
- Add regression coverage showing the generic walker skips the redundant Hugging Face subtree while `registry_snapshot()` still discovers the same Hugging Face cache model.

## Performance Probe

Build a synthetic Hugging Face cache root with many `models--*/snapshots/*` directories and compare repeated registry rescans against an `origin/main` baseline helper. Success means identical discovered model IDs with lower repeated-rescan wall time and/or fewer directory enumeration calls for the optimized branch.

## Verification Commands

- `PYTHONPATH=<repo>:<repo>/services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `PYTHONPATH=<repo>:<repo>/services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `coverage json -o coverage.json`
- changed-scope coverage script against `worker/model_registry/catalog.py`
- synthetic performance probe comparing `origin/main` logic to branch logic
- `git diff --check`
