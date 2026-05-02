# PR-scoped registry cache-key fast path

## Scope

This slice targets the Python PR-scoped performance registry loader. The hot
path repeatedly loads `infra/perf/pr_scoped_probes.json` while building scope
reports and running registered probes. The existing registry cache already avoids
re-reading unchanged JSON, but each cache lookup still canonicalizes the path via
`Path.resolve()`.

## Optimization

Use an absolute normalized cache key for `load_probe_registry()` instead of a
full filesystem-resolving key. The cache still validates entries with `stat()`
mtime and size before reuse, preserving stale-cache protection while avoiding
repeated path resolution overhead on registry-cache hits.

## Registered probe

The affected path is covered by `pr-scoped-performance-registry-cache` in
`infra/perf/pr_scoped_probes.json` with focused `test_command`,
`coverage_command`, and `probe_command` entries. This slice also makes the probe
command explicit in the registry so local and CI evidence can invoke the same
registered command directly.

## Verification plan

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_registry_cache_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_load_probe_registry_uses_absolute_cache_key_without_resolving services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_load_probe_registry_reuses_cached_payload_when_file_is_unchanged services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_load_probe_registry_refreshes_cache_when_file_changes services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_registry_cache_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_registry_cache_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_load_probe_registry_uses_absolute_cache_key_without_resolving services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_load_probe_registry_reuses_cached_payload_when_file_is_unchanged services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_load_probe_registry_refreshes_cache_when_file_changes services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_registry_cache_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id pr-scoped-performance-registry-cache --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/pr_registry_cache_probe.json
git diff --check
```

CI remains the merge gate for the registered PR-scoped performance report.
