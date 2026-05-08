# Benchmark queue sort-key attrgetter slice

## Context

`BenchmarkQueueStore.list_records()` returns queue records in deterministic
`created_at_unix_ms, queue_item_id` order. The path is covered by the registered
PR-scoped performance probe `benchmark-queue-decoded-record-cache` in
`infra/perf/pr_scoped_probes.json`, including focused tests, changed-scope
coverage, and a probe command.

## Slice

Replace the per-call lambda sort key allocation in the queue listing hot path
with a module-level `operator.attrgetter` sort key. This keeps ordering and
public clone boundaries unchanged while reducing repeated warm-cache listing
work.

## Verification

Use the registered probe and focused queue tests:

- `services/mlx-worker-python/tests/test_benchmark_queue.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py` registered
  probe checks for `benchmark-queue-decoded-record-cache`
- registered changed-scope coverage command from `infra/perf/pr_scoped_probes.json`
- registered benchmark queue probe on Linux and PR-scoped performance CI
