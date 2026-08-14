# Release gates M9 count local bindings

## Scope

This Python-only performance slice is limited to the M9 release-gate section
metric evaluator in `services/mlx-worker-python/worker/productization/release_gates.py`.

The evaluator already returns missing and threshold-failure counts in one pass.
This slice keeps failure messages, ordering, and summary counts unchanged while
binding the hot builtins used for numeric threshold checks (`isinstance` and
`float`) once per section evaluation.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`release-gates-m9-failure-count-single-pass` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/productization/release_gates.py`
- `services/mlx-worker-python/tests/test_release_gates.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/release_gates_m9_failure_count_probe.py`

## Verification Plan

Run the registered focused tests, changed-scope coverage, and registered probe
locally on Linux before pushing. GitHub Actions PR-scoped performance remains the
merge gate for the registered probe report.

## 2026-08-14 Follow-up: Absent Prefix Root Fast Path

This follow-up keeps the same registered probe and narrows the hot missing-metric
branch in `_evaluate_section_metrics_with_counts(...)`. The M9 evaluator now
marks its generated rule set as already prefixed, so when a prefixed M9 rule name
is absent and the flat metrics payload does not contain the prefix root (e.g.
`m9`), the evaluator records the miss directly instead of rechecking whether the
missing key has the section prefix for every rule. Nested lookup is still
preserved when the root is present and for generic calls that may mix unprefixed
dotted rule names.

## Acceptance Criteria

- M9 release-gate failure messages and summary counters remain unchanged.
- Focused release-gates tests pass.
- Changed-scope coverage for the touched release-gates/probe scope remains at or
  above the repository threshold.
- The registered probe shows lower or acceptable elapsed time without increasing
  suffix/endswith checks.
