# Changed-scope coverage empty allowlist short-circuit

This Python performance slice is limited to `scripts/changed_scope_coverage.py`.

## Scope

When `MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON` filters every requested path out
of a PR-scoped coverage check, the command can return the existing empty-success
summary without loading `coverage.json` or invoking `git diff`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`changed-scope-coverage-empty-path-short-circuit` in
`infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`,
`coverage_command`, and `probe_command` entries for
`scripts/changed_scope_coverage.py`, `scripts/changed_scope_coverage_probe.py`,
`tests/test_changed_scope_coverage.py`, and the PR-scoped performance registry
tests.

This slice extends the existing probe to include the command-level empty
allowlist path and to count whether the coverage JSON file is read.

The 2026-06-17 follow-up slice keeps the same behavior but recognizes the
literal empty JSON array (`[]`) before invoking the JSON decoder, which is the
common no-paths-remaining value used by probe-scoped coverage checks.

## Verification plan

1. Run the registered focused tests locally on Linux.
2. Run the registered coverage command locally on Linux.
3. Run the registered probe locally and compare the command-level empty allowlist
   metrics against `origin/main`.
4. Use GitHub Actions and the PR-scoped registered probe report as the merge
   source of truth.
