# Job Registry Active Manifest Tuple Cache

## Scope

This performance slice is limited to the Python model-ops job registry active derived-model manifest accessor.

Affected files:

- `services/mlx-worker-python/worker/model_ops/job_registry.py`
- `services/mlx-worker-python/tests/test_model_ops_job_registry.py`

## Registered Probe

The affected path is covered by the existing PR-scoped probe `job-registry-derived-model-single-pass` in `infra/perf/pr_scoped_probes.json`.

The registered probe includes focused `test_command`, `coverage_command`, and `probe_command` entries. Its `active_manifest_elapsed_ms_mean` metric repeatedly calls `ModelOpsJobRegistry.active_derived_model_manifests()` after cache warmup, so it directly measures this slice.

## Implementation Plan

1. Add a regression assertion that repeated `active_derived_model_manifests()` calls reuse the cached manifest tuple and still invalidate when derived-model activity changes.
2. Cache the manifest tuple alongside the active row cache instead of rebuilding a tuple from cached rows on every call.
3. Keep the existing row, derived-model-id, and manifest-path cache invalidation path as the single invalidation point.
4. Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux before opening a PR.

## Validation Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_job_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_job_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/job_registry.py services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/job_registry_derived_model_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/job_registry_derived_model_probe.py
```

CI remains the merge gate for the registered PR-scoped performance report.
