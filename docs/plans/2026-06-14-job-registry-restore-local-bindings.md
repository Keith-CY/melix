# Job Registry Restore Local Bindings

## Scope

This Python-only performance slice is limited to the model-ops job registry restore hot loop:

- `services/mlx-worker-python/worker/model_ops/job_registry.py`
- `services/mlx-worker-python/tests/test_model_ops_job_registry.py`
- `scripts/job_registry_restore_probe.py`

The slice does not change restored job ordering, duplicate handling, manifest payload semantics, or generated protocol artifacts.

## Registered PR-scoped probe

Affected path coverage is provided by the registered probe `job-registry-restore-sort-elision` in `infra/perf/pr_scoped_probes.json`. The registry entry already has focused `test_command`, `coverage_command`, and `probe_command` entries and reports:

- `restore_elapsed_ms_mean` (`lower_is_better`)
- `per_manifest_ms_mean` (`lower_is_better`)

## Implementation plan

1. Keep the existing exact-operation fast path and fallback normalization behavior unchanged.
2. Reduce repeated attribute/global lookups inside `_restore_manifest_jobs(...)` by binding stable helpers, the jobs dictionary, the job type, and the stage tuple once per restore call.
3. Reuse the registered focused tests, changed-scope coverage, and local Linux probe to verify behavior and performance.

## Validation commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_job_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_restore_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_job_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_restore_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/job_registry.py services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/job_registry_restore_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/job_registry_restore_probe.py
```

CI remains the merge gate for the registered PR-scoped performance report.
