# Worker registry loaded-model order cache

## Goal

Reduce repeated sorting work in `WorkerRegistry` when callers request loaded model handles and loaded model summaries without changing output ordering or runtime behavior.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python`, so focused tests, changed-scope coverage, and the registered PR-scoped performance probe are locally verifiable on Linux.

## Touched files

- `services/mlx-worker-python/worker/registry.py`
- `services/mlx-worker-python/tests/test_runtime_edges.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- `scripts/worker_registry_resident_probe.py`
- `docs/plans/2026-05-03-worker-registry-loaded-model-order-cache.md`

## Optimization hypothesis

`list_loaded_models()` and `list_loaded_model_summaries()` currently sort the loaded-model handle set independently. A small invalidation-based ordered-handle cache inside `WorkerRegistry` should preserve the same lexicographic order while avoiding repeated `sorted(...)` work across back-to-back listing calls and repeated reads between registry mutations.

## Registered probe

This path remains covered by `worker-registry-resident-bytes-accumulator` in `infra/perf/pr_scoped_probes.json`. The probe will be updated to emit concrete loaded-model listing metrics in addition to the existing resident-bytes and runtime-stats metrics.

## Success metrics

- Preserve loaded-model ordering and summary payloads exactly.
- Changed executable scope coverage must be `>=95%`.
- Local probe must emit concrete loaded-model listing metrics and show fewer sort calls than `origin/main`.
- PR-scoped CI probe `worker-registry-resident-bytes-accumulator` must validate the same path before merge.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_worker_registry_sparse_model_request_fast_path_preserves_semantics \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_registry_capabilities_and_request_lifecycle \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_runtime_stats_request_counters_stay_consistent_without_request_scan \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_worker_registry_avoids_rescanning_loaded_models_for_resident_bytes \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_worker_registry_reuses_sorted_handles_across_listing_calls \
  services/mlx-worker-python/tests/test_runtime_service.py::test_load_model_returns_handle_and_lists_model \
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
  services/mlx-worker-python/tests/test_runtime_edges.py::test_worker_registry_reuses_sorted_handles_across_listing_calls \
  services/mlx-worker-python/tests/test_runtime_service.py::test_load_model_returns_handle_and_lists_model \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_runtime_service_handles_failures_and_state_transitions \
  services/mlx-worker-python/tests/test_runtime_edges.py::test_runtime_service_rejects_model_loads_that_exceed_process_budget_and_reports_headroom \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_worker_registry_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_worker_registry_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/registry.py \
  services/mlx-worker-python/tests/test_runtime_edges.py \
  services/mlx-worker-python/tests/test_runtime_service.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/worker_registry_resident_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py \
  --registry infra/perf/pr_scoped_probes.json \
  --probe-id worker-registry-resident-bytes-accumulator \
  --base-repo <baseline-worktree> \
  --head-repo "$PWD" \
  --output /tmp/worker_registry_loaded_model_cache_probe.json

git diff --check
```
