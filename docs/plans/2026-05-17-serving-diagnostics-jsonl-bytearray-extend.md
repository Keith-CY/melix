# Serving diagnostics JSONL bytearray extend slice

## Scope

This Python-only performance slice targets the empty-attribute serving diagnostics JSONL fast path in `services/mlx-worker-python/worker/productization/serving_diagnostics.py`.

The affected path is covered by the registered PR-scoped performance probe `serving-diagnostics-debug-queue-bounds` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the serving diagnostics implementation, focused unit tests, PR-scoped probe tests, and `scripts/serving_diagnostics_queue_probe.py`.

## Optimization

The previous writer built each fast-path event row as a temporary `bytes` object via the direct helper and then extended the output buffer. This slice keeps the public direct helper for tests and compatibility, but lets `_write_jsonl(...)` append the known JSON fragments directly into the shared `bytearray`.

This removes one per-row `bytes.join(...)` allocation on the common decode/completed empty-attribute event path while preserving the JSON field order, request-id literal cache, numeric literal caches, fallback behavior, and event bundle schema.

## Verification plan

1. Add a focused regression test proving `_write_jsonl(...)` no longer depends on the per-row join helper for the fast path.
2. Run focused serving diagnostics tests and PR-scoped probe registry tests.
3. Run changed-scope coverage for the touched implementation and test files.
4. Run the registered `serving-diagnostics-debug-queue-bounds` probe locally on Linux before and after the change.
5. Let the PR-scoped performance workflow validate the registered probe in CI before merge.

## Metrics

Primary metric: `serialization_elapsed_ms_mean` from `serving-diagnostics-debug-queue-bounds` (lower is better). Secondary metric: `elapsed_ms_mean` should not regress materially because queue append behavior is unchanged.

Local Linux probe samples with `MELIX_SERVING_DIAGNOSTICS_QUEUE_SAMPLES=20` showed the serialization mean moving from roughly `1.107274 ms` on `origin/main` to roughly `0.994488 ms` after the change across three repeated probe runs. CI remains the registered validation source for merge.
