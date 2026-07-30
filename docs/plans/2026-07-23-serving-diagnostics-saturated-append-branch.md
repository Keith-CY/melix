# Serving Diagnostics Saturated Append Branch

## Scope

This Python-only performance slice keeps serving diagnostics debug queue behavior
unchanged while reducing overhead on the hot saturated append path in
`services/mlx-worker-python/worker/productization/serving_diagnostics.py`.

The affected path is already covered by the registered PR-scoped performance
probe `serving-diagnostics-debug-queue-bounds` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for the serving
diagnostics implementation, tests, and
`scripts/serving_diagnostics_queue_probe.py`.

## Planned Change

The bounded debug queue spends most probe iterations after the deque has reached
capacity. Split the saturated branch before the retained-count path so overflow
appends avoid re-entering the unsaturated branch body and keep the retained count
stable after capacity is reached. The queue still acquires the same lock before
mutating the deque or dropped count, so snapshot serialization remains
consistent.

## Behavior Invariants

- Queue capacity remains bounded by `max_events`.
- Overflow appends still drop the oldest retained event through the bounded
  deque and return `False`.
- `dropped_count` still counts overflow events.
- `snapshot()` still returns a tuple of retained events and the dropped count.
- Bundle manifests and JSONL event serialization remain byte-compatible for the
  same retained events.

## Verification Plan

1. Run focused serving diagnostics queue tests and the registered probe script
   test.
2. Run changed-scope coverage for serving diagnostics and PR-scoped performance
   registry tests.
3. Run the registered `serving-diagnostics-debug-queue-bounds` probe locally on
   Linux with repeated samples before and after the change.
4. Use GitHub Actions PR-scoped performance as the CI validation source before
   merging.

## Metrics

Primary metric: `elapsed_ms_mean` from `serving-diagnostics-debug-queue-bounds`
(lower is better). Secondary metrics: `serialization_elapsed_ms_mean` and
`serialized_bytes` should not regress materially because serialization behavior
is unchanged.
