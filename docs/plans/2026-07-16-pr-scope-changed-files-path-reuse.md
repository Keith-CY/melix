# PR Scope Changed-Files Cache Performance Slice

## Scope

This Python-only performance slice is limited to `scripts/pr_scoped_performance_scope.py` and the changed-files JSON loader used before PR-scoped probe selection.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `pr-scoped-performance-scope-json-read-bytes` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries and runs locally on Linux.

## Plan

1. Preserve the changed-files JSON list validation and CLI output semantics.
2. Reuse exact `Path` inputs instead of always re-wrapping them with `Path(path)`, while preserving string path support through the fallback wrapper.
3. Cache parsed changed-files payloads by path, mtime, and size so repeated scope-preparation calls can skip JSON decoding while still invalidating when the file changes.
4. Return a fresh list from cache so callers cannot mutate the cached tuple.
5. Keep the focused test tied to the registered probe and cover cache reuse, mutation isolation, string input, and file-change invalidation.
6. Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux before opening the PR.

## Metrics

Local Linux validation must include the registered probe output with old/new mean timings and changed-scope coverage for the touched files. GitHub Actions PR-scoped performance remains the merge gate after the PR is opened.
