# PR-scoped registry scope os.stat slice

## Scope

This Python-only slice targets the scope registry metadata check in
`services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.
`build_scope_report()` calls `load_probe_registry_for_scope()` for every scoped
PR-performance selection. The current hot path already normalizes the registry
path to an absolute cache key, so this slice avoids constructing a `Path` and
calling `Path.stat()` only to recover the same file metadata.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`pr-scoped-performance-registry-cache` in `infra/perf/pr_scoped_probes.json`.
That registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries covering:

- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Implementation

Use `_probe_registry_cache_key(path)` directly in `load_probe_registry_for_scope()`
and stat the resulting absolute string with `os.stat(cache_key)`. This keeps
cache invalidation based on `(mtime_ns, size)` unchanged while removing the
scope-only `Path(path)` allocation and `Path.stat()` method dispatch.

## Verification plan

Run the focused registry-cache tests, changed-scope coverage, and the registered
local probe on Linux before pushing. The PR-scoped performance workflow remains
the merge gate for the registered probe report in CI.

## Success metric

Accept the slice only if the registered probe reports directionally lower
`build_scope_report_ms_mean` without regressing correctness tests or
changed-scope coverage. `load_probe_registry_ms_mean` and
`cold_load_probe_registry_ms_mean` are expected to be neutral because the slice
only touches the scope loader path.
