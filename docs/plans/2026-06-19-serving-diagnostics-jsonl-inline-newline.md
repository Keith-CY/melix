# Serving Diagnostics JSONL Inline Newline Performance Slice

## Scope

This slice keeps the serving diagnostics debug queue behavior unchanged while
reducing the hot JSONL serialization path for empty-attribute events. The writer
now lets the fast-path extender append a complete JSONL line, including the
trailing newline, so `_write_jsonl()` avoids one extra `bytearray.extend()` call
for every fast-path event.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`serving-diagnostics-debug-queue-bounds` in `infra/perf/pr_scoped_probes.json`.
The registry entry already provides focused `test_command`, `coverage_command`,
and `probe_command` coverage for:

- `services/mlx-worker-python/worker/productization/serving_diagnostics.py`
- `services/mlx-worker-python/tests/test_serving_diagnostics.py`
- `scripts/serving_diagnostics_queue_probe.py`

## Verification plan

- Run the focused registered serving diagnostics test command locally on Linux.
- Run the registered changed-scope coverage command locally on Linux.
- Run `scripts/serving_diagnostics_queue_probe.py` locally on Linux against both
  `origin/main` and the slice worktree with the same sample count.
- Use GitHub Actions PR-scoped performance workflow as the final registered CI
  validation before merge.

## Expected outcome

The serialized JSONL bytes, retained/dropped queue counts, and event payloads
remain unchanged. The local probe should show a lower `elapsed_ms_mean` and a
lower `serialization_elapsed_ms_mean`, with `serialized_bytes` unchanged.
