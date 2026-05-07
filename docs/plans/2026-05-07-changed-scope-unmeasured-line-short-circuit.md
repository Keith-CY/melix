# Changed-scope coverage unmeasured-line short circuit

## Goal

Avoid reading source files in `scripts/changed_scope_coverage.py` when a touched path has changed lines, but none of those changed lines are present in the coverage report's measured line set.

## Scope

This slice is limited to the Python changed-scope coverage helper and its registered PR-scoped probe:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_probe.py`
- `tests/test_changed_scope_coverage.py`
- `infra/perf/pr_scoped_probes.json`

## Registered probe

The affected path is covered by the registered PR-scoped probe `changed-scope-coverage-empty-path-short-circuit`. This slice extends the probe scenario from a strictly empty changed-line set to a non-empty changed-line set whose lines are unmeasured by coverage. The probe records:

- `elapsed_ms_mean`
- `source_read_calls_mean`

## Implementation plan

1. Compute the intersection between changed lines and coverage-measured lines before loading source text.
2. Return empty measurable/covered/missed lists immediately when the intersection is empty.
3. Keep the existing source-line filtering behavior unchanged for measured changed lines.
4. Update regression tests and the probe fixture to prove no source read occurs for unmeasured changed lines.

## Verification

- Focused changed-scope coverage tests pass.
- Changed-scope coverage for touched executable files is at least 95%.
- The registered local probe reports `source_read_calls_mean == 0.0` and a lower `elapsed_ms_mean` versus the `origin/main` baseline for the unmeasured-line scenario.
- `git diff --check` passes.
