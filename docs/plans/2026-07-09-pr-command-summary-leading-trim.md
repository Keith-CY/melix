# PR-scoped command summary leading-trim slice

## Scope

This Python performance slice is limited to `_summarize_command` in
`worker.productization.pr_scoped_performance`. The PR-scoped performance runner
logs compact command summaries for long focused test, coverage, and probe
commands. Multi-line command heredocs can be large, so copying the entire string
with `str.strip()` before selecting the first line adds avoidable allocation work
on every summary call.

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`pr-scoped-performance-scope-matcher` in `infra/perf/pr_scoped_probes.json`. The
probe has focused `test_command`, `coverage_command`, and `probe_command` entries
and includes a repeated command-summary workload with a large multi-line command
payload.

## Implementation plan

1. Keep `_summarize_command` output identical for empty, single-line, multi-line,
   whitespace-padded, and truncated commands.
2. Replace the eager whole-string `strip()` with index-based leading/trailing
   whitespace bounds plus a bounded first-newline search.
3. Reuse the existing command-summary regression tests and the registered probe
   to validate behavior and local Linux performance.

## Verification

Run the registered focused tests, changed-scope coverage, and local registered
probe on Linux before pushing. GitHub Actions PR-scoped performance remains the
merge gate for the registered probe report.
