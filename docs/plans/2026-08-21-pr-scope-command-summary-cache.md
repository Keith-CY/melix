# PR-scoped command summary cache

## Scope

This Python-only performance slice is limited to `_summarize_command(...)` in
`services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.
The helper renders compact command summaries for PR-scoped performance command
heartbeats and is exercised by the scope matcher probe's repeated command-summary
micro workload.

## Probe Coverage

The affected path is covered by the registered PR-scoped performance probe
`pr-scoped-performance-scope-matcher` in `infra/perf/pr_scoped_probes.json`.
That registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries and reports `command_summary_ms_mean`, so no new probe
registration is required for this slice.

## Plan

1. Keep command summary output semantics unchanged for empty, single-line,
   multi-line, and max-length cases.
2. Cache compact command summaries by command text and max length so repeated
   heartbeat/probe formatting for identical commands avoids re-trimming and
   re-scanning large command payloads.
3. Run the registered focused test command, changed-scope coverage command, and
   registered probe locally on Linux.
4. Use PR-scoped performance CI as the merge gate for the registered probe result.

## Success Criteria

- Focused tests for PR-scoped performance command summaries pass.
- Changed-scope coverage remains at or above the repository threshold.
- The registered `pr-scoped-performance-scope-matcher` probe reports a lower
  `command_summary_ms_mean` for the candidate branch versus `origin/main`.
- PR-scoped performance CI completes successfully before merge.
