# 2026-04-29 Benchmark Queue Scan Optimization

## Summary

Optimize the Linux-verifiable Python benchmark queue scan path by removing unnecessary glob pattern work and centralizing queue record loading in `services/mlx-worker-python/worker/productization/benchmark_queue.py`.

## Scope

- `services/mlx-worker-python/worker/productization/benchmark_queue.py`
- `services/mlx-worker-python/tests/test_benchmark_queue.py`

## Constraints

- Linux host only; no Swift or macOS-only validation.
- Keep the change to one small optimization slice.
- Preserve queue record ordering and on-disk JSON format.

## Optimization Goal

Reduce repeated directory-scan overhead in `BenchmarkQueueStore.list_records()` and remove duplicate file->JSON->record parsing logic shared with `transition()`.

## Planned Change

1. Add a shared helper that loads a queue record from a JSON file path.
2. Replace `queue_root.glob("*.json")` with direct `queue_root.iterdir()` filtering for `*.json` files.
3. Keep behavior identical for missing directories, non-file entries, sorting, and transitions.
4. Add a regression test proving non-JSON files and JSON-named directories are ignored.

## Follow-up Slice: Append Binding

The 2026-07-26 follow-up slice keeps the registered benchmark queue cache probe
and narrows implementation to one hot-loop binding in
`BenchmarkQueueStore.list_records()`: bind `records.append` once before the
`os.scandir()` loop and call the local in the per-entry JSON-file path. This
preserves queue ordering, metadata cache semantics, and public clone behavior
while shaving repeated attribute lookup overhead from large queue scans.

## Performance Probe

Use a synthetic queue directory with thousands of JSON queue item files plus noise files. Measure elapsed time for:

- current `glob("*.json")` scan strategy
- optimized `iterdir()` + suffix filter strategy

Success metric: optimized probe is measurably faster while returning the same record count.

## Verification Commands

```bash
cd services/mlx-worker-python
PYTHONPATH=/tmp/melix-cron-python-opt-20260429-192455:/tmp/melix-cron-python-opt-20260429-192455/services/mlx-worker-python pytest -q tests/test_benchmark_queue.py
PYTHONPATH=/tmp/melix-cron-python-opt-20260429-192455:/tmp/melix-cron-python-opt-20260429-192455/services/mlx-worker-python coverage run -m pytest -q tests/test_benchmark_queue.py
PYTHONPATH=/tmp/melix-cron-python-opt-20260429-192455:/tmp/melix-cron-python-opt-20260429-192455/services/mlx-worker-python coverage report -m worker/productization/benchmark_queue.py tests/test_benchmark_queue.py
python3 <probe script>
git diff --check
```
