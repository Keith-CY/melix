# Changed-Scope Coverage Range Guard

## Slice

This Python-only performance slice is limited to `scripts/changed_scope_coverage.py`, specifically `_measurable_changed_lines()` when a changed line set is entirely outside the executed/missing line ranges reported by coverage.py.

## Registered probe

The affected path is covered by the registered PR-scoped probe `changed-scope-coverage-measured-set-filter` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries and runs on `ubuntu-latest`.

## Optimization

Before constructing `set(executed_lines)` and `set(missing_lines)` for multi-line coverage entries, compute the covered line range from the sorted coverage.py line lists. If the changed line set is below or above that range, return early without allocating the lookup sets or reading source text.

This preserves behavior for in-range changed lines, blank/comment filtering, single-line fast paths, and empty coverage entries.

## Verification plan

1. Run the focused changed-scope coverage tests plus registry tests.
2. Run changed-scope coverage for the changed files and registered probe support paths.
3. Run the registered probe locally on Linux against `origin/main` and this branch.
4. Use PR-scoped performance CI as the final registered probe gate before merge.

## Local evidence

Local Linux registered probe (`changed-scope-coverage-measured-set-filter`):

- `elapsed_ms_mean`: base `2.3197705325271403 ms`, head `0.29483065009117126 ms`, delta `-2.024939882435969 ms` (`~87.29%` faster)
- `source_read_calls_mean`: base `0.0`, head `0.0`
- coverage: `100.0%` changed-scope coverage
