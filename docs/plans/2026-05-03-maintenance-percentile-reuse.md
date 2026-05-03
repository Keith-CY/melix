# Maintenance percentile reuse optimization plan

## Goal

Reduce redundant sorting work in `services/mlx-worker-python/worker/engine/maintenance_core.py` by reusing one sorted latency vector when the code needs multiple percentiles from the same sample set.

## Linux-only constraint

This slice is limited to the Python worker and PR-scoped performance configuration so it can be verified locally on Linux without macOS or Swift execution.

## Touched files

- `services/mlx-worker-python/worker/engine/maintenance_core.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Implementation sketch

1. Add a helper that computes multiple percentiles from one sorted sample vector while preserving existing rounding and interpolation semantics.
2. Route the repeated p50/p95 maintenance paths through that helper:
   - top-level `RunBench` request latency summary
   - matrix summary `ttft` and request latency summaries
   - latency-suite metric emission
3. Add focused regression tests that prove these paths no longer fall back to repeated percentile helper calls.
4. Register a dedicated PR-scoped performance probe for the maintenance percentile path.

## Performance probe

Register `maintenance-percentile-vector-reuse` in `infra/perf/pr_scoped_probes.json`.

Probe definition:
- build a synthetic list of request latencies
- compare the hot path that needs p50 and p95 from the same vector
- report concrete elapsed metrics for repeated samples
- keep the probe command base-compatible by embedding it inline in the registry command

## Success metrics

- No behavior change in percentile outputs.
- Changed-scope automated coverage >= 95%.
- Local probe shows lower mean elapsed time for the repeated percentile workload.
- `git diff --check` passes.

## Verification commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_run_bench_latency_and_summary_reuse_single_sorted_request_latency_vector \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_run_bench_matrix_reuses_single_sorted_latency_vectors \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_percentiles_reuse_one_sorted_vector_and_preserve_interpolation \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_run_bench_measures_runtime_behavior_from_loaded_backend \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_run_bench_matrix_returns_summary_rows_and_persists_matrix_artifacts \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_maintenance_percentile_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_run_bench_latency_and_summary_reuse_single_sorted_request_latency_vector \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_run_bench_matrix_reuses_single_sorted_latency_vectors \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_percentiles_reuse_one_sorted_vector_and_preserve_interpolation \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_run_bench_measures_runtime_behavior_from_loaded_backend \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_run_bench_matrix_returns_summary_rows_and_persists_matrix_artifacts \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_maintenance_percentile_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/engine/maintenance_core.py \
  services/mlx-worker-python/tests/test_maintenance_service.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python bash -lc '<maintenance percentile probe command from registry>'

git diff --check
```