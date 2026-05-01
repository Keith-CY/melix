# Worker Registry Resident-Bytes Accumulator Optimization Plan

## Goal

Avoid repeated `sum(...)` scans across `WorkerRegistry._loaded_models` during model loads and runtime stats collection by maintaining an incrementally updated resident-bytes accumulator.

## Linux Constraint

This slice is Python-only and will be verified locally on Linux. No macOS-only runtime behavior is required for acceptance.

## Touched Files

- `services/mlx-worker-python/worker/registry.py`
- `services/mlx-worker-python/tests/test_runtime_edges.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- `scripts/worker_registry_resident_probe.py`

## Probe Definition

Probe id: `worker-registry-resident-bytes-accumulator`

The probe will:
1. build a `WorkerRegistry` with the lightweight fake backend from `test_runtime_edges`
2. preload a large number of loaded models
3. repeatedly run a `load_model()` + `runtime_stats()` + `unload_model()` cycle
4. emit JSON metrics with concrete timing and resident-byte invariants

## Success Metrics

- Preserve resident-byte accounting and memory-budget behavior exactly.
- Changed executable scope coverage must be `>=95%`.
- Probe must emit stable JSON metrics that can run on both `origin/main` and the branch.
- Head branch should reduce mean elapsed time for the synthetic loaded-model cycle relative to `origin/main`.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_worker_registry_avoids_rescanning_loaded_models_for_resident_bytes \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_runtime_service_handles_failures_and_state_transitions \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_runtime_service_rejects_model_loads_that_exceed_process_budget_and_reports_headroom \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_worker_registry_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_worker_registry_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_worker_registry_avoids_rescanning_loaded_models_for_resident_bytes \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_runtime_service_handles_failures_and_state_transitions \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_runtime_service_rejects_model_loads_that_exceed_process_budget_and_reports_headroom \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_worker_registry_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_worker_registry_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/registry.py \
  services/mlx-worker-python/tests/test_runtime_edges.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/worker_registry_resident_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/worker_registry_resident_probe.py
```

## Notes

This is a small behavior-preserving optimization slice. No protocol or lockfile changes are expected.
