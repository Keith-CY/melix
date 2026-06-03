# Changed Scope Coverage Bounds Fast Path

## Scope

This Python-only performance slice narrows the measured-line filtering path in
`scripts/changed_scope_coverage.py`. When a file has changed lines entirely
outside the coverage-reported executed/missing line ranges, the tool can return
an empty changed-line coverage result without materializing per-line lookup sets.

Affected paths:

- `scripts/changed_scope_coverage.py`
- `tests/test_changed_scope_coverage.py`
- `docs/plans/2026-06-03-changed-scope-coverage-bounds.md`

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`changed-scope-coverage-measured-set-filter` in
`infra/perf/pr_scoped_probes.json`. The registry entry already provides focused
`test_command`, `coverage_command`, and `probe_command` entries for this path.

## Implementation Plan

1. Add an explicit bounds helper that checks whether any coverage measured-line
   group can overlap the changed-line range.
2. Use the bounds helper before building executed/missing membership sets in
   `_measurable_changed_lines()`.
3. Add focused unit coverage for disjoint and overlapping bounds behavior.
4. Run the registered focused tests, changed-scope coverage command, and the
   registered local probe on Linux.

## Success Metrics

- Focused tests pass.
- Changed-scope coverage for touched Python lines remains at least 95%.
- The registered probe reports lower `elapsed_ms_mean` for the no-overlap large
  measured-line workload while preserving zero source reads.

## Verification Boundary

This is a Python tooling slice and is locally verifiable on Linux. It does not
change Swift runtime behavior.
