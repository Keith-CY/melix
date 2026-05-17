# Changed-scope coverage diff newline split performance slice

## Scope

This slice targets only `scripts/changed_scope_coverage.py` diff parsing for
changed-scope coverage reports. The parser consumes `git diff --unified=0`
output, which is newline-delimited text produced by Git.

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

Use the Git diff newline delimiter directly (`split("\n")`) instead of the
more general `splitlines()` helper in the hot parser loop. The parser only needs
Git's `\n` line separator, so this avoids the extra universal-newline handling
while preserving changed-line results for the existing diff fixtures and probe
shape.

## Validation plan

1. Run the focused changed-scope coverage tests.
2. Run changed-scope coverage for the touched files.
3. Run the registered `changed-scope-coverage-diff-parser` probe locally on
   Linux and compare against the pre-change baseline.
4. Require the PR-scoped performance workflow to run the registered probe in CI
   before merge.
