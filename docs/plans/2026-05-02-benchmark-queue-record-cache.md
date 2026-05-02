# Benchmark Queue Record Cache Optimization Plan

## Goal

Reduce redundant JSON parsing in `BenchmarkQueueStore.list_records()` by reusing decoded queue records when the underlying queue-item file has not changed between repeated polls.

## Constraints

- Work from Linux only.
- Keep the slice Python-only and locally verifiable.
- Preserve queue ordering, file format, transition semantics, and error behavior.
- Keep the cache worktree-local/in-memory only; do not change persisted payload shapes.

## Performance Probe

Probe ID: `benchmark-queue-decoded-record-cache`

Measure repeated `BenchmarkQueueStore.list_records()` scans across a synthetic queue directory with many stable JSON records.

Success metrics:
- lower `warm_elapsed_ms_mean`
- lower `warm_json_loads_mean`
- preserve `record_count`

## Files Expected

- `services/mlx-worker-python/worker/productization/benchmark_queue.py`
- `services/mlx-worker-python/tests/test_benchmark_queue.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- `scripts/changed_scope_coverage.py` (read-only, reused by coverage command)

## Task 1

Implement a metadata-keyed decoded-record cache for benchmark queue records.

Requirements:
- cache decoded `BenchmarkQueueRecord` values inside `BenchmarkQueueStore`
- key cache reuse on stable file metadata so changed files are reloaded automatically
- invalidate or refresh cache entries on enqueue/transition writes
- preserve current sort order and failure behavior when files disappear or become unreadable
- add focused tests proving unchanged files avoid redundant JSON loads while changed files still reload
- register a PR-scoped performance probe for the touched path with focused test and changed-scope coverage commands

## Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_queue.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_queue_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_benchmark_queue_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_queue_cache_rejects_unexpected_record_count

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_benchmark_queue.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_queue_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_benchmark_queue_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_queue_cache_rejects_unexpected_record_count && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/benchmark_queue.py services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_benchmark_queue.py services/mlx-worker-python/tests/test_pr_scoped_performance.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_benchmark_queue_cache as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"

git diff --check
```