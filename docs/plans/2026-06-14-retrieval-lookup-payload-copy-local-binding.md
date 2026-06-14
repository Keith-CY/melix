# Retrieval Lookup Payload Copy Local Binding

## Summary

This slice keeps retrieval lookup projection behavior unchanged and narrows one
Python hot path: copying nested lookup payload values in
`worker.runtime.retrieval_context._copy_payload` / `_copy_payload_value`.

The affected path is already covered by the registered PR-scoped probe
`retrieval-context-projection-fastpath`, which includes focused tests,
changed-scope coverage, and a JSON performance probe command.

## Probe Coverage

Registered probe: `retrieval-context-projection-fastpath`

Affected files covered by the probe registry:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/retrieval_context_projection_probe.py`

## Implementation

Bind `_copy_payload_value` to a local variable before dict/list/tuple
comprehensions in the recursive copy helper. This removes repeated global name
lookups while preserving the same exact-type copy semantics and the `deepcopy`
fallback for unknown value types.

## Validation Plan

Run the registered focused tests, changed-scope coverage command, and registered
probe locally on Linux. The PR-scoped performance workflow remains the source of
truth for the CI probe report before merge.
