# Stream assembler legacy pipe body whitespace fast path

## Context

The standard pipe parser keeps a compatibility path for legacy hidden-channel
headers where the channel header also carries reasoning body text. That path
slices the body after the channel name and only needs to distinguish an empty or
whitespace-only body from a body with content.

## Slice

Replace the legacy hidden pipe body truth check from `body.strip()` to
`body and not body.isspace()` so non-empty content avoids allocating a stripped
copy of the body. Preserve existing semantics for empty, whitespace-only,
visible, and unknown channel headers.

## Registered Probe

Use the existing `stream-assembler-structural-prefix-cache` PR-scoped probe. The
probe already watches `services/mlx-worker-python/worker/runtime/stream_assembler.py`
and runs focused stream assembler tests, changed-scope coverage, and the
registered probe command. This slice extends the probe with
`legacy_pipe_body_elapsed_ms_mean` so the changed compatibility path is measured
alongside the existing structural-prefix metrics.

## Verification Plan

1. Add a regression test proving `_legacy_pipe_channel_header_body()` does not
   call `strip()` on content bodies and still rejects whitespace-only hidden
   headers and visible channels.
2. Run the focused regression test.
3. Run the registered `stream-assembler-structural-prefix-cache` `test_command`.
4. Run the registered `coverage_command` and confirm changed-scope coverage is
   at least 95%.
5. Run the registered local probe against `origin/main` and the branch, then use
   GitHub Actions PR-scoped performance as the merge gate.
