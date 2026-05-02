# Job registry manifest-path lookup cache

## Scope

This Linux-verifiable Python performance slice targets `services/mlx-worker-python/worker/model_ops/job_registry.py` only. It keeps derived-model resolution semantics unchanged while narrowing the hot path for `ModelOpsJobRegistry.resolve_derived_model_target(manifest_path=...)`.

## Registered probe

The affected path is covered by the existing PR-scoped probe `job-registry-derived-model-single-pass` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- `test_command` for focused job-registry behavior tests and PR-scoped probe registration tests.
- `coverage_command` for changed-scope coverage across `job_registry.py`, its focused tests, PR-scoped performance tests, and the probe script.
- `probe_command` via `scripts/job_registry_derived_model_probe.py`, now reporting `manifest_path_elapsed_ms_mean` in addition to active-manifest and model-id lookup timings.

## Optimization

Before this slice, model-id resolution used a cached dictionary, but manifest-path-only resolution still iterated active derived-model rows and resolved each activation manifest path until it found a match. This slice adds a sibling cache keyed by resolved activation manifest path and invalidates it together with the existing active-row/model-id caches.

## Verification plan

Run from the repository root:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_job_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_job_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/job_registry.py services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/job_registry_derived_model_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/job_registry_derived_model_probe.py
```

CI remains the merge gate for the registered PR-scoped performance report.
