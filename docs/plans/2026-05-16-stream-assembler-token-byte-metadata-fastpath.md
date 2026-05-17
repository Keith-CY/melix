# Stream Assembler Token-Byte Metadata Fast Path

## Scope

This slice narrows the Python stream assembler hot path for fragments that carry
`token_bytes` without token ids or logprobs. That is the common synthetic and
adapter path covered by the registered PR-scoped probe
`stream-assembler-token-byte-fast-decode`.

Affected files:

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `scripts/stream_assembler_token_bytes_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Registered probe

The affected path is already covered by the PR-scoped registered probe
`stream-assembler-token-byte-fast-decode` in
`infra/perf/pr_scoped_probes.json`. The registry entry defines focused
`test_command`, `coverage_command`, and `probe_command` entries and watches the
stream assembler implementation, focused stream assembler tests, the
PR-scoped-performance selection tests, and the token-byte probe script.

The primary metric is `elapsed_ms_mean` with `lower_is_better`; peak bytes are
also tracked as a lower-is-better guardrail, and generated token count remains
informational to prove behavior parity.

## Implementation plan

1. Keep token-byte decoding semantics unchanged, including split multibyte
   fallback behavior and raw text materialization.
2. Add a narrow metadata accounting branch for fragments that only include
   `token_bytes`, avoiding the generic token metadata helper on that hot path.
3. Reuse the existing focused regression tests for complete ASCII token bytes and
   split multibyte token bytes.
4. Run the registered focused test command, changed-scope coverage command, and
   registered probe locally on Linux before opening the PR.
5. Use GitHub Actions and the registered PR-scoped performance report as the
   merge gate.

## Success criteria

- Focused tests and changed-scope coverage pass with at least 95% coverage for
  the touched scope.
- The registered token-byte probe preserves `generated_token_count_mean` and
  improves or holds `elapsed_ms_mean` relative to `origin/main`.
- CI PR-scoped performance validation completes successfully before merge.
