# Stream Assembler Extra Token Round Distribution

## Goal

Reduce per-token Python loop overhead in the stream assembler token-count annotation path while preserving the existing round-robin distribution semantics for extra generated-token counts.

## Affected path

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `scripts/stream_assembler_token_bytes_probe.py`
- `infra/perf/pr_scoped_probes.json`

The affected runtime path is covered by the registered PR-scoped probe `stream-assembler-token-byte-fast-decode`. The registry entry already provides focused `test_command`, `coverage_command`, and `probe_command` entries and watches the files above.

## Slice

`RequestStreamAssembler._distribute_extra_delta_tokens(...)` previously assigned extra tokens one at a time with a modulo cursor over the selected priority indexes. This slice computes the complete round count with `divmod(extra_tokens, len(priority_indexes))`, adds full rounds to each priority index once, then applies the remainder to the first priority indexes.

Behavior stays equivalent:

- tool-call deltas remain the highest-priority extra-token targets;
- reasoning deltas remain the fallback priority when there are no tool calls;
- visible/content deltas remain the fallback when neither tool nor reasoning deltas exist;
- remainder ordering remains the same as the prior cursor-based round-robin loop.

## Verification plan

Run on Linux:

1. Focused regression test for batched round-robin extra-token distribution.
2. Registered focused `stream-assembler-token-byte-fast-decode` test command.
3. Registered changed-scope coverage command.
4. Registered local performance probe, compared against an `origin/main` baseline for `token_count_annotation_ms_mean`.
5. PR-scoped performance CI remains the merge gate.

## Metrics

Primary local metric: `token_count_annotation_ms_mean` from `scripts/stream_assembler_token_bytes_probe.py` (lower is better). Guardrails remain `elapsed_ms_mean`, `delta_token_count_new_ms_mean`, and `peak_bytes_mean` from the same registered probe.
