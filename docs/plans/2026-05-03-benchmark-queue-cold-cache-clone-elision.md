# Benchmark queue cold cache clone elision

## Goal

Reduce the uncached `BenchmarkQueueStore.list_records()` path in `services/mlx-worker-python/worker/productization/benchmark_queue.py` by removing a redundant clone during cache-miss decode, while preserving returned-record defensive copies, stable ordering, cache invalidation semantics, and the existing PR-scoped performance evidence path.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python`, so it can be fully verified from this Linux host without touching macOS or Swift surfaces.

## Touched files

- `services/mlx-worker-python/worker/productization/benchmark_queue.py`
- `services/mlx-worker-python/tests/test_benchmark_queue.py`

## Optimization hypothesis

`list_records()` already clones each returned record at the public API boundary. On a cache miss, `_load_record()` currently decodes a `BenchmarkQueueRecord`, clones it once to populate `_decoded_record_cache`, and returns that cloned copy. `list_records()` then clones the same record again before returning it to the caller.

This slice stores the decoded record itself in the cache on cache misses and keeps the defensive clone at the public return boundary. That should reduce cold-path object copying without weakening mutation isolation for callers.

## Verification path

Use the existing `benchmark-queue-decoded-record-cache` PR-scoped performance probe in `infra/perf/pr_scoped_probes.json`.

### Focused checks

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_benchmark_queue.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_queue_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_benchmark_queue_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_queue_cache_rejects_unexpected_record_count

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_benchmark_queue.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_queue_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_benchmark_queue_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_queue_cache_rejects_unexpected_record_count
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/benchmark_queue.py \
  services/mlx-worker-python/tests/test_benchmark_queue.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_benchmark_queue_cache as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"

git diff --check
```

## Success criteria

- Focused tests pass.
- Changed-scope automated coverage is at least 95%.
- Local probe reports concrete cold/warm metrics and keeps `warm_json_loads_mean` at `0.0`.
- Hosted `benchmark-queue-decoded-record-cache` PR-scoped CI validates the same path before merge.
