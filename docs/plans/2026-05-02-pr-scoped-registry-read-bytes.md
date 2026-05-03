# PR-scoped registry JSON read-bytes fast path

## Scope

This slice targets the Python PR-scoped performance registry loader in
`services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.
The loader parses `infra/perf/pr_scoped_probes.json` when the registry cache is
cold or invalidated. The previous cache-key slice already avoids repeated reads
on cache hits; this slice keeps that behavior and trims the cold-read path.

## Optimization

Read the registry JSON payload with `Path.read_bytes()` and pass the bytes
directly to `json.loads()`. This avoids the intermediate UTF-8 text decode that
`Path.read_text()` performs before JSON parsing while preserving the same JSON
validation and cache invalidation semantics.

## Registered probe

The affected path is covered by `pr-scoped-performance-registry-cache` in
`infra/perf/pr_scoped_probes.json`. The registered probe includes focused
`test_command`, `coverage_command`, and `probe_command` entries, and it measures
`cold_load_probe_registry_ms_mean`, `load_probe_registry_ms_mean`, and
`build_scope_report_ms_mean`.

## Verification plan

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_registry_cache_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_load_probe_registry_uses_absolute_cache_key_without_resolving services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_load_probe_registry_reuses_cached_payload_when_file_is_unchanged services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_load_probe_registry_refreshes_cache_when_file_changes services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_registry_cache_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_registry_cache_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_load_probe_registry_uses_absolute_cache_key_without_resolving services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_load_probe_registry_reuses_cached_payload_when_file_is_unchanged services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_load_probe_registry_refreshes_cache_when_file_changes services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_registry_cache_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id pr-scoped-performance-registry-cache --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/pr_registry_read_bytes_probe.json
git diff --check
```

CI remains the merge gate for the registered PR-scoped performance report.
