# Changed-scope coverage overlap helper no-varargs slice

## Scope

This Python-only performance slice targets `scripts/changed_scope_coverage.py`.
The affected path is covered by the registered PR-scoped probe
`changed-scope-coverage-measured-set-filter` in `infra/perf/pr_scoped_probes.json`.
The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries and is locally verifiable on Linux.

## Hypothesis

`_measurable_changed_lines()` calls `_line_ranges_may_overlap()` once per
candidate path during changed-scope coverage checks. The helper always receives
the same two measured line groups (`executed_lines` and `missing_lines`), but the
current helper accepts `*measured_line_groups`, allocating a short varargs tuple
on every path. Replacing that helper with an explicit two-group signature keeps
behavior identical while removing repeated tuple allocation from the measured-set
filter hot path.

## Verification

- Focused pytest for changed-scope coverage behavior and PR-scoped registry tests.
- Changed-scope coverage for `scripts/changed_scope_coverage.py`,
  `tests/test_changed_scope_coverage.py`, `services/mlx-worker-python/tests/test_pr_scoped_performance.py`,
  and `scripts/changed_scope_coverage_measured_probe.py`.
- Registered local probe:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/changed_scope_coverage_measured_probe.py`.
- CI must run the registered PR-scoped performance probe before merge.

## Linux Boundary

This slice touches a repository script and Python tests only. It is locally
validated on Linux; no Swift runtime effect is claimed.
