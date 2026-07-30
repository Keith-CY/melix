# Stream assembler single-delta token-count bypass

## Scope

This Python-only performance slice is limited to `RequestStreamAssembler._annotate_token_counts()` in `services/mlx-worker-python/worker/runtime/stream_assembler.py`.

The helper is exercised for every accepted stream fragment that carries token accounting. Single-delta, single-token fragments are the common fast path for token-byte streaming and do not require wrapper allocation or list replacement.

## Registered probe

The affected path is covered by the registered PR-scoped probe `stream-assembler-token-byte-fast-decode` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and reports `elapsed_ms_mean`, `generated_token_count_mean`, and token-count annotation/compression metrics for this stream assembler path.

## Plan

1. Preserve token-count annotation semantics for empty, single-delta, and multi-delta streams.
2. Return the existing single-delta list directly when the incoming `token_count` is already one.
3. Add focused regression coverage for the single-delta single-token bypass and the existing multi-token wrapper behavior.
4. Run focused tests, changed-scope coverage, and the registered token-byte probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate after PR creation.

## Success criteria

- Focused stream assembler tests pass.
- Changed-scope coverage remains at least 95 percent for the touched scope.
- The registered token-byte probe shows non-regressed stream assembly metrics and records the single-token fast path with `generated_token_count_mean` unchanged.