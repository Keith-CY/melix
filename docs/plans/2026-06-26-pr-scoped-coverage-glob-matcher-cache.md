# PR-scoped Coverage Glob Matcher Cache

## Context

`coverage_paths_for_probe()` runs for each selected PR-scoped performance probe when
building the scope report. The path already has the registered
`pr-scoped-performance-scope-matcher` probe, including focused tests,
changed-scope coverage, and a local/CI `probe_command` for the large scope
matching workload.

## Slice

This slice keeps behavior unchanged and only optimizes coverage path selection:

- build exact watch-path sets and compiled wildcard matchers once per probe
  `watch_globs` tuple;
- let exact watch paths use set membership instead of rescanning raw globs;
- reuse compiled wildcard matchers through the existing compiled glob matcher
  helper.

No registry semantics, force-all behavior, probe selection behavior, protocol
artifacts, or generated files change. The registered performance gate for this
slice tracks `build_scope_report_ms_mean`, `selected_probe_count_mean`, and
`force_all_selected_mean`; the pre-existing command-summary microprobe remains
covered by focused tests but is not part of this slice's gating metrics because
it measures CI log summarization rather than scope matching.

## Verification Plan

Run the registered `pr-scoped-performance-scope-matcher` focused test command,
its changed-scope coverage command, and the registered probe locally on Linux.
GitHub Actions remains the merge gate for the PR-scoped performance report.
