# Stream assembler token-byte pending fast path

This Python performance slice is limited to `RequestStreamAssembler._token_byte_delta` in `services/mlx-worker-python/worker/runtime/stream_assembler.py`.

## Scope

- Preserve token-byte assembly semantics for complete ASCII, complete multibyte, split multibyte, and invalid UTF-8 fragments.
- Keep the complete-token hot path on direct `bytes.decode()` without constructing the incremental decoder.
- Avoid the extra `bool()` conversion on every complete token-byte fragment by branching directly on the pending-byte buffer and only materializing the `had_pending` flag on fallback paths.
- Use the existing `stream-assembler-token-byte-fast-decode` registered PR-scoped probe as the local and CI performance gate.

## Verification plan

- Focused pytest for token-byte fast decode and fallback behavior.
- Changed-scope coverage through the registered probe `coverage_command`.
- Registered PR-scoped performance probe command for `stream-assembler-token-byte-fast-decode`.
- Local before/after probe comparison on Linux; CI remains the repository merge gate for the registered probe report.

## Metrics

Expected local effect is lower CPU time for complete token-byte streams in the registered probe while preserving generated token counts and byte-fallback metrics.
