# Benchmark queue string cache key

## Goal

Reduce warm-cache overhead in the Python benchmark queue record listing path by avoiding per-entry `Path` construction when `os.DirEntry` metadata already proves that the cached decoded record is still valid.

## Scope

- `services/mlx-worker-python/worker/productization/benchmark_queue.py`
- `services/mlx-worker-python/tests/test_benchmark_queue.py`
- Registered probe: `benchmark-queue-decoded-record-cache` in `infra/perf/pr_scoped_probes.json`

## Plan

1. Keep `BenchmarkQueueStore.list_records()` on the existing `os.scandir()` path.
2. Key the decoded-record cache by filesystem string path so `entry.path` can be used directly on the warm list path.
3. Preserve defensive copies at public return boundaries and existing cache invalidation by metadata key.
4. Add regression coverage proving the warm list path does not construct `Path` objects after a cache hit.
5. Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux before PR creation.

## Performance Probe

The affected path is already covered by the registered PR-scoped probe `benchmark-queue-decoded-record-cache`, including:

- `test_command`
- `coverage_command`
- `probe_command`

Primary metrics remain `cold_elapsed_ms`, `warm_elapsed_ms_mean`, and `warm_json_loads_mean`. The expected improvement is in `warm_elapsed_ms_mean`; `warm_json_loads_mean` should remain `0.0` for warm-cache reads.

## Validation Boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime validation is required for this slice.
