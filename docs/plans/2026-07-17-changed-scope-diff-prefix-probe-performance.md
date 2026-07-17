# Changed-Scope Diff Prefix Probe Performance Slice

## Scope

Optimize exactly one Python hot path in `scripts/changed_scope_coverage.py`:
`_parse_changed_lines`, the changed-scope coverage unified-diff parser used by
coverage gates and the PR-scoped performance workflow.

The affected path is already covered by the registered PR-scoped performance
probe `changed-scope-coverage-diff-parser` in `infra/perf/pr_scoped_probes.json`.
That registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries.

## Slice

Keep the parser behavior unchanged while reducing repeated hot-loop work for
header and hunk detection:

- bind the byte hunk new-range marker once before the loop; and
- use the bytes prefix predicate for diff header detection instead of slicing a
  new prefix-length bytes object for each candidate header line.

## Verification Plan

- Run the registered focused test command for
  `changed-scope-coverage-diff-parser`.
- Run the registered changed-scope coverage command and require at least 95%
  coverage for the touched scope.
- Run the registered probe command locally on Linux and compare it against an
  `origin/main` baseline from the same host.
- Let GitHub Actions run the PR-scoped performance workflow before merge.

## Boundary

This is a Linux-verifiable Python slice. No Swift runtime effect is claimed.
