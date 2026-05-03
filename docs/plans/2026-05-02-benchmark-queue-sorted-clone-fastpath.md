# BenchmarkQueue sorted clone fast path performance slice

## Goal

Reduce warm `BenchmarkQueueStore.list_records()` Python overhead by avoiding the generator-based clone-sort path, while preserving JSON filtering, regular-file filtering, record ordering, cache invalidation semantics, and returned-record defensive copies.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python`, so it can be fully verified from this Linux host without touching macOS/Swift surfaces.

## Touched files

- `services/mlx-worker-python/worker/productization/benchmark_queue.py`

## Optimization hypothesis

`list_records()` already materializes decoded records into a local list. Sorting clones through `sorted((clone(record) for record in records), key=...)` adds generator and sorted-list construction overhead before returning the defensive copies.

This slice sorts the local cached-record list in place, then returns a list comprehension of defensive clones. The returned values remain independent copies, and ordering remains `(created_at_unix_ms, queue_item_id)`.

A rejected trial in this worktree attempted to reuse `DirEntry.stat()` metadata for the cache key. Local registered probe samples were worse than the current baseline, so that approach was reverted before this accepted slice.

## Registered probe

The affected path is covered by `benchmark-queue-decoded-record-cache` in `infra/perf/pr_scoped_probes.json`. The entry includes focused `test_command`, `coverage_command`, and `probe_command` values and measures:

- `warm_elapsed_ms_mean` (lower is better)
- `warm_json_loads_mean` (lower is better; should remain zero for cached warm reads)

## Verification commands

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
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/benchmark_queue.py \
  services/mlx-worker-python/worker/productization/pr_scoped_performance.py \
  services/mlx-worker-python/tests/test_benchmark_queue.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 /tmp/melix_benchmark_queue_probe.py

git diff --check
```

## Success criteria

- Focused tests pass.
- Changed-scope automated coverage is at least 95%.
- Local registered probe reports concrete metrics and keeps `warm_json_loads_mean` at `0.0`.
- PR-scoped CI probe `benchmark-queue-decoded-record-cache` validates the same path before merge.
