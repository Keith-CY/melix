# Stream Assembler Compressed Token Round Batching

## Goal

Reduce per-token Python loop overhead in the stream assembler token-count annotation path when the assembler must compress many estimated delta token counts down to a smaller generated-token total.

## Affected path

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `scripts/stream_assembler_token_bytes_probe.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

The affected runtime path is covered by the registered PR-scoped probe `stream-assembler-token-byte-fast-decode`. This slice extends that existing registered probe with `token_count_compression_ms_mean` so the compressed-token branch is measured directly in local Linux runs and in PR-scoped performance CI.

## Slice

`RequestStreamAssembler._compress_delta_token_counts(...)` previously assigned remaining compressed-token capacity one token at a time across all deltas that still had extra capacity. This slice keeps the same round-robin order but batches full rounds across the active indexes, drops saturated indexes, and only falls back to single-index remainder assignment when fewer than one full round remains.

Behavior stays equivalent:

- every delta starts with one token until the generated-token total is lower than the delta count;
- deltas with larger estimated weights retain extra capacity before smaller deltas saturate;
- round-robin order across active deltas remains stable;
- saturated deltas stop receiving additional compressed tokens.

## Verification plan

Run on Linux:

1. Focused regression test for batched compressed-token distribution.
2. Registered focused `stream-assembler-token-byte-fast-decode` test command.
3. Registered changed-scope coverage command.
4. Registered local performance probe, compared against an `origin/main` baseline for `token_count_compression_ms_mean`.
5. PR-scoped performance CI remains the merge gate.

## Metrics

Primary local metric: `token_count_compression_ms_mean` from `scripts/stream_assembler_token_bytes_probe.py` (lower is better). Guardrails remain `elapsed_ms_mean`, `delta_token_count_new_ms_mean`, `token_count_annotation_ms_mean`, and `peak_bytes_mean` from the same registered probe.
