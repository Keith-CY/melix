# Changed-scope source line fast path

## Scope

This Python-only performance slice is limited to `scripts/changed_scope_coverage.py`
source-line measurability checks. The behavior stays identical for blank lines,
full-line comments, and indented code/comment lines, while common unindented
source lines avoid constructing a stripped copy before being counted as
measurable.

## Registered probe

The affected path is covered by the registered PR-scoped probes in
`infra/perf/pr_scoped_probes.json`:

- `changed-scope-coverage-measured-set-filter`
- `changed-scope-coverage-singleton-range-fastpath`

Both entries include focused `test_command`, `coverage_command`, and
`probe_command` values for the changed-scope coverage script, regression tests,
and JSON-emitting performance probes.

## Implementation plan

1. Add or preserve regression coverage proving blank lines, direct comments,
   indented comments, and indented code keep the same measurable-line behavior.
2. Add a narrow first-character fast path inside `_measurable_non_comment_lines()`
   so common non-indented non-comment source lines are accepted without `strip()`.
3. Run the registered focused tests, changed-scope coverage, and the measured and
   singleton registered probes locally on Linux before opening the PR.
4. Use GitHub Actions PR-scoped performance as the merge gate for the registered
   probe report.

## Metrics

Success requires focused pytest passing, changed-scope coverage at or above the
95% repository requirement for the touched scope, and the registered local/CI
probes showing directionally lower or non-regressive elapsed time for the source
line measurement workloads.
