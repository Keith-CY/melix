# Changed-Scope Parser Local ASCII Bindings Performance Slice

## Scope

Optimize exactly one Python hot path in the changed-scope coverage diff parser:
`_parse_changed_lines` in `scripts/changed_scope_coverage.py`.

The affected path is already covered by the registered PR-scoped performance
probe `changed-scope-coverage-diff-parser` in
`infra/perf/pr_scoped_probes.json`. That probe includes focused
`test_command`, `coverage_command`, and `probe_command` entries and measures
`elapsed_ms_mean` for a synthetic multi-file unified diff.

## Slice

Bind the parser's frequently used ASCII byte marker constants to local names
before the inner diff-line loop. This keeps the parser behavior unchanged while
removing repeated global lookups for the hot branch dispatch checks.

## Verification Plan

- Run the registered focused test command for
  `changed-scope-coverage-diff-parser`.
- Run the registered changed-scope coverage command and require at least 95%
  coverage for the touched scope.
- Run the registered probe command locally on Linux and compare against an
  `origin/main` baseline from the same host.
- Let GitHub Actions run the PR-scoped performance workflow before merge.

## Boundary

This is a Linux-verifiable Python slice. No Swift runtime effect is claimed.
