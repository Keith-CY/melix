# Deterministic Embedding Cycle Copy Method Binding

## Slice

This Python-only performance slice targets the repeated multi-input cycle branch
in `services/mlx-worker-python/worker/runtime/deterministic_embedding_runtime.py`.
The existing path already detects a repeated cycle and replays copied vectors;
this slice reduces per-replayed-vector method lookup overhead by binding each
cycle vector's `copy` method once after the first cycle is embedded.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`deterministic-embedding-duplicate-input-cache` in
`infra/perf/pr_scoped_probes.json`. The registry entry has focused
`test_command`, `coverage_command`, and `probe_command` fields and watches:

- `services/mlx-worker-python/worker/runtime/deterministic_embedding_runtime.py`
- `services/mlx-worker-python/tests/test_embedding_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/deterministic_embedding_duplicate_probe.py`

## Verification plan

1. Run the registered focused test command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered probe locally on Linux before and after the change and
   compare `elapsed_ms_mean`, `peak_bytes_mean`, and `embed_text_calls_mean`.

## Expected behavior

The runtime must still return one vector per input, keep repeated vectors as
separate mutable lists, and preserve the reduced backend call count for repeated
cycles. The registered probe asserts vector count, checksum, duplicate copy
identity, and backend call count.
