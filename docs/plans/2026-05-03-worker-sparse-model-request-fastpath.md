# Worker registry sparse model request fast path

## Goal

Reduce Python overhead in `WorkerRegistry.load_model()` for model-id-only load requests without changing catalog resolution or full `ModelSpec` behavior.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python`, so focused tests, changed-scope coverage, and the registered PR-scoped performance probe are locally verifiable on Linux.

## Touched files

- `services/mlx-worker-python/worker/registry.py`
- `services/mlx-worker-python/tests/test_runtime_edges.py`
- `infra/perf/pr_scoped_probes.json`
- `docs/plans/2026-05-03-worker-sparse-model-request-fastpath.md`

## Optimization hypothesis

`WorkerRegistry._is_sparse_model_request()` currently builds a temporary set of populated protobuf field names before checking whether the request only contains `model_id`. The common catalog-resolution hot path only needs to distinguish three cases: no populated fields, one populated `model_id` field, or anything else. Checking the `ListFields()` result length and first descriptor name avoids the set allocation on every `load_model()` call while preserving sparse-request semantics.

## Registered probe

The affected path is covered by `worker-registry-resident-bytes-accumulator` in `infra/perf/pr_scoped_probes.json`. The registered entry already includes focused `test_command`, `coverage_command`, and `probe_command` values and measures:

- `elapsed_ms_mean` (lower is better)
- `request_stats_elapsed_ms_mean` (lower is better)

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_worker_registry_sparse_model_request_fast_path_preserves_semantics \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_registry_capabilities_and_request_lifecycle \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_runtime_stats_request_counters_stay_consistent_without_request_scan \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_worker_registry_avoids_rescanning_loaded_models_for_resident_bytes \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_runtime_service_handles_failures_and_state_transitions \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_runtime_service_rejects_model_loads_that_exceed_process_budget_and_reports_headroom \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_worker_registry_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_worker_registry_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_worker_registry_sparse_model_request_fast_path_preserves_semantics \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_registry_capabilities_and_request_lifecycle \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_runtime_stats_request_counters_stay_consistent_without_request_scan \
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

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py \
  --registry infra/perf/pr_scoped_probes.json \
  --probe-id worker-registry-resident-bytes-accumulator \
  --base-repo <baseline-worktree> \
  --head-repo "$PWD" \
  --output /tmp/worker_registry_sparse_model_probe.json

git diff --check
```

## Success criteria

- Focused tests pass.
- Changed-scope automated coverage is at least 95%.
- Local registered probe reports concrete metrics and does not regress `request_stats_elapsed_ms_mean`.
- PR-scoped CI probe `worker-registry-resident-bytes-accumulator` validates the same path before merge.
