# PR-scoped Command Summary Streaming

## Context

The PR-scoped performance runner emits compact command summaries for CI heartbeat logs via `worker.productization.pr_scoped_performance._summarize_command`. The current implementation strips every line into a list before it only uses the first non-empty line and whether a second non-empty line exists. Long registered probe commands can contain large heredocs, so this repeats avoidable line splitting and list allocation on every heartbeat/log prefix.

Registered probe coverage already exists for the affected path through `pr-scoped-performance-scope-matcher` in `infra/perf/pr_scoped_probes.json`, with focused test, coverage, and probe commands. This slice extends that existing probe with a command-summary timing metric so the changed hot path is measured directly.

## Slice

1. Preserve `_summarize_command` output semantics for empty, single-line, multi-line, and truncated commands.
2. Stream-scan only until the first two non-empty lines are known, avoiding allocation of all stripped command lines.
3. Add/adjust focused tests for leading blank multi-line commands and probe metric presence.
4. Extend the registered PR-scoped probe metric list with `command_summary_ms_mean`.

## Verification

- Focused pytest for command summary and PR-scoped probe behavior.
- Changed-scope coverage using the registered `pr-scoped-performance-scope-matcher` coverage command.
- Registered PR-scoped performance probe comparing `origin/main` baseline against this branch.

## Acceptance

Accept only if behavior tests pass, changed-scope coverage remains >=95%, and the registered probe reports a clear command-summary timing improvement without regressing scope-matcher semantics.
