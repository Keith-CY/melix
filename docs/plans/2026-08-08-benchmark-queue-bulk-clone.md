# Benchmark queue positional clone slice

This Python-only performance slice keeps benchmark queue semantics unchanged while reducing constructor dispatch overhead in the record-clone hot path.

## Affected path

- `services/mlx-worker-python/worker/productization/benchmark_queue.py`
- `services/mlx-worker-python/tests/test_benchmark_queue.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

The affected path is covered by the registered PR-scoped probe `benchmark-queue-decoded-record-cache`. The registry entry already provides focused `test_command`, `coverage_command`, and `probe_command` entries for benchmark queue listing and decoded-record cache behavior.

## Optimization

`BenchmarkQueueStore._clone_record()` still returns a new `BenchmarkQueueRecord` and still copies the mutable `parameters` mapping. This slice switches the constructor call from keyword arguments to positional arguments so the warm queue listing path avoids repeated keyword mapping setup for every returned cloned record.

Behavior is intentionally equivalent:

- records are still sorted by `created_at_unix_ms` and `queue_item_id`;
- each public record returned by enqueue, transition, and list operations remains a clone;
- each returned `parameters` mapping remains copied and isolated from the decoded-record cache.

## Verification plan

Run on Linux:

1. Focused benchmark queue tests and PR-scoped probe selection tests through the registered focused command.
2. Changed-scope coverage through the registered coverage command.
3. Registered benchmark queue probe locally with the registry command, comparing `origin/main` baseline to this slice.
4. GitHub Actions PR-scoped performance as the merge gate.

## Metrics

Primary metric: `warm_elapsed_ms_mean` from the registered `benchmark-queue-decoded-record-cache` probe. Secondary metrics: `cold_elapsed_ms`, `cold_json_loads`, `record_count`, and `warm_json_loads_mean`.
