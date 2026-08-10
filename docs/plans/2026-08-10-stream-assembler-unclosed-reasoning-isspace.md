# Stream assembler unclosed reasoning whitespace fast path

## Context

The stream assembler recovery path for malformed or unclosed reasoning sections
first checks whether the buffered reasoning body is empty. The previous guard
used `body.strip()`, which can allocate a stripped copy for content-bearing
bodies that ultimately do not contain any visible-tail recovery markers.

## Slice

Replace the initial empty-body check in `_recover_unclosed_reasoning_body(...)`
with `not body or body.isspace()`. This preserves empty and whitespace-only
handling, while content-bearing bodies avoid the preliminary stripped copy. The
existing `strip()` calls for returned hidden/visible marker splits remain in
place because they define the emitted recovery text.

## Registered Probe

Use the existing `stream-assembler-structural-prefix-cache` PR-scoped probe. It
already covers `services/mlx-worker-python/worker/runtime/stream_assembler.py`
with focused `test_command`, `coverage_command`, and `probe_command` entries.
This slice extends that registered probe with
`unclosed_reasoning_recovery_elapsed_ms_mean` so the changed recovery path is
measured locally and by CI.

## Verification Plan

1. Add a regression test proving `_recover_unclosed_reasoning_body(...)` does
   not call `strip()` for content-bearing bodies without recovery markers and
   still treats whitespace-only bodies as empty.
2. Run the focused regression test and the registered structural-prefix
   `test_command`.
3. Run the registered changed-scope `coverage_command` and confirm at least 95%
   coverage for touched files.
4. Run the registered probe locally against `origin/main` and the branch, then
   use the GitHub Actions PR-scoped performance report as the merge gate.
