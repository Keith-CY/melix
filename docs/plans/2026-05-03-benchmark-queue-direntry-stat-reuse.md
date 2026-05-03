# Benchmark queue DirEntry stat reuse

## Goal

Reduce filesystem metadata overhead in the Python benchmark queue record listing path by reusing the `os.DirEntry.stat()` result gathered while filtering queue JSON files.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python`, so it is locally verifiable on Linux with focused tests, changed-scope coverage, and the registered PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/productization/benchmark_queue.py`
- `services/mlx-worker-python/tests/test_benchmark_queue.py`

## Optimization hypothesis

`BenchmarkQueueStore.list_records()` scans queue directories with `os.scandir()`, filters JSON files, and then calls `_metadata_key(path)`, which performs a separate `Path.stat()` for each record. A single `DirEntry.stat()` call can both confirm the entry is a regular file and provide the metadata key used for decoded-record cache invalidation.

Reusing that stat payload should preserve cache semantics while removing the extra per-record path stat from the list path.

## Registered probe

Use the existing `benchmark-queue-decoded-record-cache` PR-scoped performance probe in `infra/perf/pr_scoped_probes.json`. It provides focused test, coverage, and probe commands for this path.

## Verification path

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
  services/mlx-worker-python/tests/test_benchmark_queue.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 /tmp/run_benchmark_queue_probe.py

git diff --check
```

## Success criteria

- Focused tests pass.
- Changed-scope automated coverage is at least 95%.
- Local probe reports concrete cold/warm metrics with `warm_json_loads_mean` at `0.0`.
- Hosted `benchmark-queue-decoded-record-cache` PR-scoped CI validates the same path before merge.
