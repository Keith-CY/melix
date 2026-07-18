# Stream Assembler Channel Name Probe Coverage

## Scope

This slice is limited to PR-scoped performance probe coverage for the Harmony channel-name hot path in `RequestStreamAssembler._pipe_channel_name(...)`.

## Registered probe

The affected stream assembler path was selected by the registered PR-scoped probe `stream-assembler-parser-mode-cache` in `infra/perf/pr_scoped_probes.json`, but the previous inline workload did not exercise Harmony channel headers. This slice updates that registered probe so the workload includes cumulative Harmony channel fragments, tracks `_pipe_channel_name(...)` calls, and keeps focused `test_command`, `coverage_command`, and `probe_command` fields for Linux CI.

## Probe-only decision

The original probe-registration slice did not include a runtime behavior optimization. A candidate implementation that replaced `split(maxsplit=1)` with a Python-level single-pass whitespace scan was rejected locally because the direct microprobe regressed (`old_mean=26.863ms`, `new_mean=58.407ms`, `speedup=0.46x`). A bounded positional split variant was also rejected because the stream-assembler workload regressed (`old_mean=3.741ms`, `new_mean=4.001ms`, `speedup=0.93x`).

## 2026-07-18 split fast path follow-up

`origin/main` now uses a Python-level `enumerate(...).isspace()` scan for `_pipe_channel_name(...)`. This follow-up returns the hot path to `header.strip().split(None, 1)[0].lower()` so whitespace tokenization runs in CPython's string split implementation while preserving behavior for empty headers, mixed-case channel names, tab-separated metadata, and headers without metadata.

The registered `stream-assembler-parser-mode-cache` probe remains the governing PR-scoped performance probe. It watches `stream_assembler.py`, `test_stream_assembler.py`, `test_pr_scoped_performance.py`, and `scripts/stream_assembler_parser_mode_probe.py`, and includes focused `test_command`, `coverage_command`, and `probe_command` entries.

Local Linux registered probe samples on this host:

- baseline `origin/main`: `4.8284132462868`, `3.7157699662202504`, `3.8718708565284032` ms; mean `4.1386846896784845` ms.
- split fast path: `4.1309146108687855`, `3.958180532208644`, `3.952636387111852` ms; mean `4.013910510063094` ms.
- delta: `-0.1247741796153905` ms, `3.014826555637104%` faster.
- `channel_name_calls_mean`: unchanged at `13.0`.

## Verification plan

1. Run the registered focused test command for `stream-assembler-parser-mode-cache`.
2. Run the registered changed-scope coverage command for the same probe.
3. Run the registered local probe on Linux and record `elapsed_ms_mean`, `harmony_channel_count`, and `channel_name_calls_mean`.
4. Use the PR-scoped performance workflow as the merge gate before future behavior slices rely on this path.

## Success metrics

- Focused tests pass.
- Changed-scope coverage for touched paths is at least 95%.
- Registered probe emits Harmony channel metrics and completes successfully in CI.
