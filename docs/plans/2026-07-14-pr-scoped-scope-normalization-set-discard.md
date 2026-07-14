# PR-scoped scope normalization set-discard slice

## Scope

This Python-only performance slice is limited to
`worker.productization.pr_scoped_performance.build_scope_report()`.
The affected path is covered by the registered
`pr-scoped-performance-scope-matcher` probe in
`infra/perf/pr_scoped_probes.json`, which includes focused `test_command`,
`coverage_command`, and `probe_command` entries.

## Plan

`build_scope_report()` normalizes changed file inputs on every PR-scoped
performance scope build. The previous normalization used a set comprehension
that filtered empty paths during construction. This slice keeps the same
observable semantics—deduplicate paths, remove the empty sentinel, and sort the
result—but builds the set directly from the input list and removes the empty
sentinel with `discard("")` once. This avoids one Python-level conditional per
changed-file entry in large PR scopes while preserving the existing sorted scope
payload.

## Verification

Run the registered focused tests, changed-scope coverage command, and the local
registered `pr-scoped-performance-scope-matcher` probe on Linux before opening
the PR. GitHub Actions PR-scoped performance remains the merge gate for the
registered probe report.
