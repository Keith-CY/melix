# Job Registry Slotted Cache Rows

## Scope

This performance slice is limited to Python model-ops job registry row objects used while restoring jobs and building active derived-model lookup caches.

Affected files:

- `services/mlx-worker-python/worker/model_ops/job_registry.py`
- `services/mlx-worker-python/tests/test_model_ops_job_registry.py`

## Registered Probe

The affected path is covered by the existing PR-scoped probe `job-registry-derived-model-single-pass` in `infra/perf/pr_scoped_probes.json`.

The registered probe includes focused `test_command`, `coverage_command`, and `probe_command` entries. Its `restore_elapsed_ms_mean`, `resolve_target_elapsed_ms_mean`, `manifest_path_elapsed_ms_mean`, and `active_manifest_elapsed_ms_mean` metrics cover the restored `ModelOpsJob` instances and active derived-model lookup cache entries touched by this slice.

## Implementation Plan

1. Keep the existing job registry data model semantics unchanged.
2. Convert `ModelOpsJob` and `_ActiveDerivedModelLookup` dataclasses to slotted dataclasses so per-row instances avoid per-object dictionaries during restore and lookup-cache construction.
3. Add regression assertions that restored/cached job rows and active lookup cache entries remain dict-less.
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
