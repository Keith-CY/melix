# Model registry plain-local manifest stat elision

## Goal

Remove redundant `manifest.json` filesystem checks from the plain-local model scan path in `services/mlx-worker-python/worker/model_registry/catalog.py` while preserving model discovery behavior.

## Why this slice

The registry root tree scanner already classifies directories with `manifest.json` into the manifest path list before `_scan_raw_model_directories(...)` processes plain-local model directories. The later `Path.is_file()` check for `resolved_path / "manifest.json"` repeats work that the earlier scan already resolved.

## Linux-only constraint

This cron run is on Linux, so the slice must stay inside Python paths that can be verified locally with focused pytest, changed-scope coverage, and a local performance probe. No macOS-only validation is required for the implementation itself.

## Touched files

- `services/mlx-worker-python/worker/model_registry/catalog.py`
- `services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Implementation tasks

1. Add a focused regression test that proves `registry_snapshot()` no longer calls `Path.is_file()` on `plain-model/manifest.json` for directories already classified by the root tree scanner.
2. Remove the redundant `manifest.json` check from `_scan_raw_model_directories(...)`.
3. Register a PR-scoped performance probe for the model-registry catalog path so CI can re-measure the slice on future changes.
4. Add focused PR-scoped-performance tests that select and validate the new probe registration.

## Performance probe

### Probe name

`model-registry-plain-local-manifest-stat-elision`

### Probe workload

- Build a synthetic registry root with many plain-local model directories.
- Run `WorkerModelCatalog.registry_snapshot(rescan=True)` multiple times.
- Track how many `manifest.json` `Path.is_file()` checks occur on the plain-local directories.
- Record elapsed milliseconds.

### Success metrics

- `manifest_is_file_calls_mean` should drop materially versus `origin/main`.
- `elapsed_ms_mean` should not regress meaningfully and ideally improves.
- Model IDs discovered by the probe workload must remain identical.

## Verification commands

- Focused pytest for the model-registry catalog and PR-scoped-performance tests.
- Changed-scope coverage report from `coverage.json` using `scripts/changed_scope_coverage.py`.
- Local explicit probe run for the model-registry catalog workload.
- `git diff --check`.
