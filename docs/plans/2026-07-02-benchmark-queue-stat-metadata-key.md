# Benchmark Queue Stat Metadata Key Fast Path

This Python-only performance slice is limited to `BenchmarkQueueStore._metadata_key_from_stat()` in `services/mlx-worker-python/worker/productization/benchmark_queue.py`.

## Registered probe

The affected path is already covered by the registered PR-scoped probe `benchmark-queue-decoded-record-cache` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/benchmark_queue.py`
- `services/mlx-worker-python/tests/test_benchmark_queue.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Slice

`os.stat_result` exposes integer metadata fields for `st_mtime_ns`, `st_size`, `st_ino`, and `st_dev`. The queue scanner already obtains one `DirEntry.stat()` result per candidate JSON record and passes it into `_metadata_key_from_stat()`. This slice removes redundant `int(...)` coercions from that hot metadata-key path while preserving the same tuple shape and cache-invalidation semantics.

## Verification plan

Run the registered focused tests, changed-scope coverage, and the registered benchmark queue probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.

Expected local commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_queue.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_queue_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_benchmark_queue_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_queue_cache_rejects_unexpected_record_count
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_benchmark_queue.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_queue_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_benchmark_queue_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_queue_cache_rejects_unexpected_record_count
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/benchmark_queue.py services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_benchmark_queue.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_benchmark_queue_cache as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"
```
