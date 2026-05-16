# Changed-scope coverage hunk prefix check performance slice

## Scope

This slice targets only the hot diff parser in `scripts/changed_scope_coverage.py`.
The parser consumes `git diff --unified=0` output and records added-line numbers
for changed-scope coverage reports.

## Probe coverage

The affected path is covered by the registered PR-scoped probe
`changed-scope-coverage-diff-parser` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `scripts/changed_scope_coverage.py`
- `tests/test_changed_scope_coverage.py`
- `scripts/changed_scope_coverage_parse_probe.py`
- PR-scoped performance registry tests

## Optimization

Keep the per-line parser dispatch minimal by localizing the diff-header prefix
constants once per parse call and replacing the hunk-header `startswith("@@")`
check in the hot loop with direct character checks after the first-character
dispatch. This preserves the existing malformed-header reset behavior while
avoiding repeated global lookups and one method call per hunk header.

## Validation plan

1. Run the focused changed-scope coverage tests.
2. Run changed-scope coverage for the touched files.
3. Run the registered `changed-scope-coverage-diff-parser` probe locally on
   Linux and compare against the pre-change baseline.
4. Require the PR-scoped performance workflow to run the registered probe in CI
   before merge.
