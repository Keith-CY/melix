# Benchmark store compact row writer cache

## Slice

Cache the compact JSON encoder used by `BenchmarkStore._write_jsonl_and_csv(...)` at module import time and materialize each CSV row before handing it to `csv.writer.writerow(...)`. This keeps the streaming artifact writer behavior unchanged while reducing per-write allocation churn in the JSONL/CSV persistence hot path.

## Probe coverage

The affected path is already covered by the registered PR-scoped performance probe `benchmark-store-matrix-streaming` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` fields and watches:

- `services/mlx-worker-python/worker/productization/benchmark_store.py`
- `services/mlx-worker-python/tests/test_benchmark_store.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/benchmark_store_probe.py`

## Validation plan

1. Run the focused registered tests for `benchmark-store-matrix-streaming`.
2. Run changed-scope coverage for the same registered command.
3. Run the registered local Linux probe before and after the implementation.
4. Use PR-scoped CI as the merge gate for the registered probe report.

## Expected impact

The behavior and serialized JSONL/CSV payloads remain unchanged. The registered probe tracks `peak_bytes_mean` for this writer path, so the expected measurable impact is lower peak memory with no row-count contract changes. Wall-clock `elapsed_ms_mean` is recorded as supporting evidence but is not the registered gate for this probe entry.
