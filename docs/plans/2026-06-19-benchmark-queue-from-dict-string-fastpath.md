# Benchmark queue from-dict string fast path

## Scope

This slice targets the Linux-verifiable Python hot path in
`services/mlx-worker-python/worker/productization/benchmark_queue.py` where
`BenchmarkQueueRecord.from_dict()` decodes persisted queue JSON records during
cold `BenchmarkQueueStore.list_records()` scans.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`benchmark-queue-cache` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- `test_command` for `test_benchmark_queue.py` and focused PR-scoped performance tests.
- `coverage_command` with changed-scope coverage for benchmark queue and probe code.
- `probe_command` that emits command JSON metrics from `_probe_benchmark_queue_cache()`.

## Optimization

Persisted benchmark queue records normally arrive from JSON with already-string
`suite_ids` and `parameters`. The previous decode path always routed through
`tuple(map(str, ...))` and a per-item `str()` dictionary comprehension. This
slice adds exact-string fast paths for the common JSON shape while preserving
fallback coercion for mixed or pair-iterable inputs.

## Validation Plan

Run the registered focused tests, changed-scope coverage, and the registered
probe locally on Linux. CI remains the authoritative registered PR-scoped probe
validation after the PR is opened.
