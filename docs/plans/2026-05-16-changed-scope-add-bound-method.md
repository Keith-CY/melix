# Changed-scope coverage parser local bindings performance slice

## Scope

This slice targets only `scripts/changed_scope_coverage.py` diff parsing for
changed-scope coverage reports. The parser consumes `git diff --unified=0`
output and records added-line numbers for each changed file.

## Probe coverage

The affected path is covered by the registered PR-scoped probe
`changed-scope-coverage-diff-parser` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `scripts/changed_scope_coverage.py`
- `tests/test_changed_scope_coverage.py`
- `scripts/changed_scope_coverage_parse_probe.py`
- PR-scoped performance registry tests

## Optimization

Keep the parser's most frequent operations local to the hot loop. Bind the
per-file `set.add` method once when a diff header selects the current
changed-file bucket, and parse hunk new-start offsets inline so each hunk avoids
an extra helper call while preserving the same malformed-header reset behavior.

## Validation plan

1. Run the focused changed-scope coverage tests.
2. Run changed-scope coverage for the touched files.
3. Run the registered `changed-scope-coverage-diff-parser` probe locally on
   Linux and compare against the pre-change baseline.
4. Require the PR-scoped performance workflow to run the registered probe in CI
   before merge.
