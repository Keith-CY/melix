# Changed-scope single-line membership fast path

## Scope

This Python-only performance slice is limited to `scripts/changed_scope_coverage.py`.
When a coverage entry exposes exactly one executed line and one missing line,
`_measurable_changed_lines` can decide disjoint changed-line sets with direct
membership checks before computing broader min/max range overlap.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`changed-scope-coverage-empty-path-short-circuit` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` values and runs
`scripts/changed_scope_coverage_probe.py`.

## Plan

1. Preserve existing changed-line coverage behavior for empty changes, single-line
   coverage entries, and multi-line coverage entries.
2. Add a focused regression test proving single-line coverage entries do not call
   the broad range-overlap helper when direct membership already proves no
   measurable line can exist.
3. Move the existing singleton membership fast path ahead of the range-overlap
   guard, leaving the range guard for multi-line coverage entries.
4. Verify with the registered focused tests, changed-scope coverage command, and
   the registered local Linux probe before using PR-scoped performance CI as the
   merge gate.

## Metrics

Success is measured by the registered probe's `elapsed_ms_mean` while preserving
`source_read_calls_mean == 0.0`. This slice is Linux-verifiable and does not
claim any Swift runtime effect.
