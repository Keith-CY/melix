# Job Registry Targeted Derived-Model Lookup

## Scope

This performance slice is limited to the Python model-ops job registry derived-model lookup path.
It keeps snapshot and active-manifest behavior unchanged while reducing work in `resolve_derived_model_target` when callers request one derived model by id or manifest path.

## Registered probe

The affected path is covered by the existing PR-scoped probe `job-registry-derived-model-single-pass` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- `test_command` for `test_model_ops_job_registry.py` and probe registry smoke tests.
- `coverage_command` for changed-scope coverage across `job_registry.py`, focused tests, and the probe script.
- `probe_command` through `scripts/job_registry_derived_model_probe.py`, reporting `active_manifest_elapsed_ms_mean`, `resolve_target_elapsed_ms_mean`, and combined `elapsed_ms_mean`.

## Implementation plan

1. Add a regression test proving derived-model id lookup does not resolve every non-matching activation path before finding the requested model.
2. Change `resolve_derived_model_target` to iterate ordered jobs directly and return on the first matching active activation row instead of materializing the full active-derived tuple.
3. Preserve removal filtering semantics by reusing `_removed_derived_targets_from_ordered_jobs` before the targeted scan.
4. Run focused tests, changed-scope coverage, and the registered probe locally on Linux before opening the PR.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_job_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_job_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/job_registry.py services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/job_registry_derived_model_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/job_registry_derived_model_probe.py
```

CI remains the merge gate for the registered PR-scoped performance report.
