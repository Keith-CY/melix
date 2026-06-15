# Retrieval Copy None Fast Path

## Summary

This Python-only performance slice keeps retrieval lookup projection behavior
unchanged and narrows one hot path in
`worker.runtime.retrieval_context._copy_payload_value()`.

The lookup payload copier is called recursively for JSON-like prompt payloads
emitted by retrieval store projection. It already returns immutable scalar
values directly and recursively copies mutable containers. This slice moves the
`None` fast path ahead of the exact-type checks so null payload fields return
immediately instead of paying the full scalar comparison chain.

## Probe Coverage

Registered probe: `retrieval-context-projection-fastpath` in
`infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` fields and watches:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/retrieval_context_projection_probe.py`

The checked-in probe reports direct projection, store-record projection, and
lookup-copy metrics, including `lookup_copy_optimized_elapsed_ms_mean` and
`lookup_copy_speedup` for the payload copy path.

## Implementation

1. Preserve recursive copy semantics for dict, list, tuple, and custom mutable
   fallback values.
2. Return `None` before computing `type(value)` and checking the other immutable
   scalar types.
3. Extend the lookup copy regression fixture with a nested null field so the
   behavior remains covered.

## Validation Plan

Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux. Use the GitHub Actions PR-scoped performance
workflow as the merge gate after opening the PR.
