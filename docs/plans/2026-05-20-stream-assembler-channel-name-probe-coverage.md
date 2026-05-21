# Stream Assembler Channel Name Probe Coverage

## Scope

This slice is limited to PR-scoped performance probe coverage for the Harmony channel-name hot path in `RequestStreamAssembler._pipe_channel_name(...)`.

## Registered probe

The affected stream assembler path was selected by the registered PR-scoped probe `stream-assembler-parser-mode-cache` in `infra/perf/pr_scoped_probes.json`, but the previous inline workload did not exercise Harmony channel headers. This slice updates that registered probe so the workload includes cumulative Harmony channel fragments, tracks `_pipe_channel_name(...)` calls, and keeps focused `test_command`, `coverage_command`, and `probe_command` fields for Linux CI.

## Probe-only decision

A candidate implementation that replaced `split(maxsplit=1)` with a Python-level single-pass whitespace scan was rejected locally because the direct microprobe regressed (`old_mean=26.863ms`, `new_mean=58.407ms`, `speedup=0.46x`). A bounded positional split variant was also rejected because the stream-assembler workload regressed (`old_mean=3.741ms`, `new_mean=4.001ms`, `speedup=0.93x`). No runtime behavior optimization is included in this PR.

## Verification plan

1. Run the registered focused test command for `stream-assembler-parser-mode-cache`.
2. Run the registered changed-scope coverage command for the same probe.
3. Run the registered local probe on Linux and record `elapsed_ms_mean`, `harmony_channel_count`, and `channel_name_calls_mean`.
4. Use the PR-scoped performance workflow as the merge gate before future behavior slices rely on this path.

## Success metrics

- Focused tests pass.
- Changed-scope coverage for touched paths is at least 95%.
- Registered probe emits Harmony channel metrics and completes successfully in CI.
