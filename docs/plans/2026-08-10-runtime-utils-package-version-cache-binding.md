# Runtime Utils Package Version Cache Binding Performance Slice

## Status

Planned for the 2026-08-10 iterative performance slice.

## Scope

Optimize the Python runtime package-version cache hit path in
`services/mlx-worker-python/worker/runtime/runtime_utils.py` by binding the
module-level version cache as a function default for `installed_package_version`.
This keeps the public cache-clear behavior unchanged while avoiding a global
cache lookup on repeated hot-path calls.

## Registered Probe

This slice is covered by the existing PR-scoped performance probe:

- `runtime-utils-package-version-cache`
- watched path: `services/mlx-worker-python/worker/runtime/runtime_utils.py`
- focused tests: `services/mlx-worker-python/tests/test_runtime_utils.py`
- coverage command: registered `coverage_command` in
  `infra/perf/pr_scoped_probes.json`
- probe command: registered `probe_command` in
  `infra/perf/pr_scoped_probes.json`

## Behavior

`installed_package_version(package_name)` continues to cache both successful
metadata lookups and missing-package results, and
`clear_installed_package_version_cache()` continues to clear the same backing
cache object. The change only narrows the lookup path for cache hits.

## Verification Plan

1. Run the focused runtime utils package-version tests and PR-scoped registry
   tests from the registered command.
2. Run changed-scope coverage using the registered coverage command.
3. Run `scripts/runtime_utils_package_version_probe.py` locally on Linux and
   compare the metrics against the pre-change baseline.
4. Let GitHub Actions run the registered PR-scoped performance workflow before
   merge.
