# Token count normalized ASCII space fast path

## Scope

This Python-only performance slice is limited to the shared deterministic
whitespace token counter used by stream assembly token accounting:
`services/mlx-worker-python/worker/runtime/token_counting.py`.

The common probe workload builds normalized ASCII token strings with single
space separators and no leading/trailing whitespace. Those strings do not need
per-character whitespace state transitions; the token count can be computed as
`space_count + 1` while preserving the existing fallback path for empty strings,
leading/trailing whitespace, repeated spaces, tab/newline/control whitespace,
and non-ASCII whitespace.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`stream-assembler-token-byte-fast-decode` in
`infra/perf/pr_scoped_probes.json`. This slice extends that probe watch list and
changed-scope coverage command to include `token_counting.py`, while reusing the
existing focused test, coverage, and probe commands for the stream assembler
hot path.

## Plan

1. Add a regression test for normalized ASCII space-separated token counts.
2. Add the smallest fast path in `whitespace_token_count()` for normalized ASCII
   text.
3. Run the focused registered test command, changed-scope coverage, and the
   registered token-byte probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the broad and registered CI merge
   gate after PR creation.

## Success criteria

- Split semantics remain unchanged for the existing ASCII, Unicode, and odd
  whitespace cases.
- Changed-scope coverage for the touched files remains at least 95 percent.
- The local registered probe improves or does not regress the token-count
  metrics, with CI PR-scoped performance as the final validation source.
