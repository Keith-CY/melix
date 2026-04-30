# Hugging Face Cache Ref Reuse Optimization Plan

## Scope
- Repository: `services/mlx-worker-python`
- Touched executable path: `worker/model_registry/catalog.py`
- Touched tests: `tests/test_model_registry_catalog.py`
- Linux-only constraint: only Python code and pytest-verifiable behavior; no Swift/macOS validation.

## Goal
Reduce redundant filesystem work during Hugging Face cache scans by reusing parsed `refs/` data once per cache repo instead of rescanning `refs/` for every snapshot revision lookup.

## Current Issue
`WorkerModelCatalog._scan_huggingface_cache_models()` iterates each snapshot under a cache repo and calls `_hf_cache_revision(cache_repo_dir, snapshot_id)` for every snapshot. `_hf_cache_revision()` currently performs a fresh `refs_dir.rglob("*")` and file reads on every call, repeating the same work across snapshots in the same repo.

## Proposed Change
- Introduce a helper that materializes a `{snapshot_id: revision_path}` mapping from `refs/` once per cache repo.
- Reuse that mapping while scanning all snapshots for the repo.
- Preserve existing fallback behavior when refs are unreadable or absent.
- Keep returned revision strings and model metadata unchanged.

## Test Plan
1. Add a focused failing test first for the reusable refs map behavior, including unreadable refs fallback.
2. Run targeted pytest to confirm the new test fails before implementation.
3. Implement the minimal catalog change.
4. Re-run targeted pytest for `tests/test_model_registry_catalog.py`.
5. Run coverage for the changed file and require at least 95% automated coverage.

## Performance Probe
Build a synthetic Hugging Face cache repo with many snapshots and refs, then compare old-vs-new revision resolution logic by timing repeated scans.

### Measurement
- wall-clock mean/median seconds across multiple scan iterations
- synthetic repo shape: one `models--org--demo` cache repo, tens to hundreds of snapshots, several ref files

### Success Metric
- identical discovered model IDs and revisions
- measurable reduction in scan time for the synthetic repeated-snapshot probe

## Verification Commands
- `PYTHONPATH=<repo>:<repo>/services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `PYTHONPATH=<repo>:<repo>/services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `coverage report -m services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `git diff --check`
