# Worker Registry Runtime Stats Single-Pass Slice

## Goal

Reduce overhead in `WorkerRegistry.runtime_stats()` when many requests are active by counting request phases and multimodal request kinds in one pass over the request table.

## Scope

- Keep request lifecycle semantics unchanged.
- Preserve active request, prefill, decode, and multimodal counters.
- Extend the existing PR-scoped worker-registry performance probe so the request-counter path is measured by CI and local Linux runs.

## Verification

Focused verification for this slice:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_runtime_edges.py::test_registry_capabilities_and_request_lifecycle services/mlx-worker-python/tests/test_runtime_edges.py::test_worker_registry_avoids_rescanning_loaded_models_for_resident_bytes services/mlx-worker-python/tests/test_runtime_edges.py::test_runtime_service_handles_failures_and_state_transitions services/mlx-worker-python/tests/test_runtime_edges.py::test_runtime_service_rejects_model_loads_that_exceed_process_budget_and_reports_headroom services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_worker_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_worker_registry_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_runtime_edges.py::test_registry_capabilities_and_request_lifecycle services/mlx-worker-python/tests/test_runtime_edges.py::test_worker_registry_avoids_rescanning_loaded_models_for_resident_bytes services/mlx-worker-python/tests/test_runtime_edges.py::test_runtime_service_handles_failures_and_state_transitions services/mlx-worker-python/tests/test_runtime_edges.py::test_runtime_service_rejects_model_loads_that_exceed_process_budget_and_reports_headroom services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_worker_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_worker_registry_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/registry.py services/mlx-worker-python/tests/test_runtime_edges.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/worker_registry_resident_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/worker_registry_resident_probe.py
```

## Metrics

The registered probe remains `worker-registry-resident-bytes-accumulator` and now also emits `request_stats_elapsed_ms_mean` for a 3,000-active-request runtime-stats loop.
