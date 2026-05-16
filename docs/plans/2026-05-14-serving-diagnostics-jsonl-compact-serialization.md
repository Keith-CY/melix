# Serving Diagnostics JSONL Compact Serialization Performance Slice

## Scope

This Python-only slice narrows the serving diagnostics debug bundle hot path by
writing event JSONL rows with compact JSON separators and batching those rows
into a single file write while preserving sorted key order and line-delimited
JSON semantics.

## Registered probe

The affected path is already covered by the PR-scoped registered probe
`serving-diagnostics-debug-queue-bounds` in `infra/perf/pr_scoped_probes.json`.
This slice extends that probe so `serialization_elapsed_ms_mean` exercises the
actual `write_serving_diagnostics_bundle(...)` JSONL writer and adds
`serialized_bytes` as a lower-is-better metric for the compact-row output.

## Linux verification plan

- Focused pytest for `services/mlx-worker-python/tests/test_serving_diagnostics.py`.
- Registered probe tests in `services/mlx-worker-python/tests/test_pr_scoped_performance.py`.
- Changed-scope coverage through the registered probe `coverage_command`.
- Registered probe command locally on Linux.

## Behavior compatibility

Events remain newline-delimited JSON objects with stable `sort_keys=True` output.
Only insignificant spaces after JSON separators are removed for the `events.jsonl`
artifact; consumers parse the same JSON object shape.
