# Changed-scope coverage dense membership slice

## Scope

This Python performance slice is limited to `scripts/changed_scope_coverage.py`, specifically `_measurable_changed_lines()` when a changed hunk touches a dense set of measured lines.

## Registered probe

The affected path is covered by the existing registered PR-scoped probe `changed-scope-coverage-measured-set-filter` in `infra/perf/pr_scoped_probes.json`.

That probe already has focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_measured_probe.py`
- `tests/test_changed_scope_coverage.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

This slice extends the existing measured probe with a dense changed-line scenario so the registered probe directly exercises the new branch.

## Optimization hypothesis

For sorted coverage line lists, `_measurable_changed_lines()` currently checks each changed line against executed and missing lists with repeated binary searches, then repeats membership checks while partitioning covered and missed lines. That is efficient for sparse changed sets, but dense changed sets can be faster by scanning the already-sorted executed and missing coverage lists once and using the changed-line set for direct membership.

The slice keeps sparse behavior unchanged and adds a dense threshold branch only when enough changed lines are present to amortize scanning coverage lists.

## Verification plan

1. Add a regression test that forces dense changed-line handling without calling `_sorted_line_list_contains()` and verifies covered/missed parity.
2. Extend `scripts/changed_scope_coverage_measured_probe.py` with dense changed-line timing.
3. Run the registered focused tests and coverage command locally on Linux.
4. Run the registered probe locally and compare dense metrics against `origin/main` with an equivalent dense scenario.

## Expected metrics

Primary metric: `dense_elapsed_ms_mean` from `scripts/changed_scope_coverage_measured_probe.py`.

Expected result: lower dense elapsed time while preserving existing sparse metrics and no source read regression for no-overlap cases.
