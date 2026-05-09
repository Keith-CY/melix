# Runtime Utils Package Version Cache

## Goal

Reduce repeated runtime metadata lookup overhead by caching package-version discovery in `worker.runtime.runtime_utils.installed_package_version(...)`.

## Linux-only constraint

This slice is Python-only and verifiable on Linux through focused pytest, changed-scope coverage, and a local PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/runtime/runtime_utils.py`
- `services/mlx-worker-python/tests/test_runtime_utils.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/runtime_utils_package_version_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Probe definition

Register `runtime-utils-package-version-cache` in the PR-scoped performance registry.

The probe repeatedly calls `installed_package_version(...)` for the same small package set while monkeypatching `importlib.metadata.version` to count metadata lookups. It reports:

- `elapsed_ms_mean` — lower is better
- `metadata_version_calls_mean` — lower is better; expected to drop to one call per unique package per sample
- `iterations_per_sample`
- `package_count`
- `sample_count`

## Success metrics

- Focused runtime utils tests pass.
- Changed-scope coverage is at least 95% for touched executable Python lines.
- Local base-vs-head probe shows reduced metadata lookup calls and improved or non-regressive elapsed time.
- `git diff --check` passes.
