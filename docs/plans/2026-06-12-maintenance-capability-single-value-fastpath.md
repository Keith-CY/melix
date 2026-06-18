# Maintenance capability single-value fast path

This Python-only performance slice is limited to capability metadata splitting in
`worker.engine.maintenance_core._split_capability_values`.

## Scope

- Preserve comma-separated capability parsing behavior, including whitespace
  trimming and empty segment dropping.
- Add a no-comma fast path for the common single capability value case so callers
  avoid allocating and iterating over a one-element `split(",")` list.
- Extend the registered PR-scoped probe to report both the existing multi-segment
  comparison and the new single-value scenario.

## Registered probe

The affected path is covered by `maintenance-capability-split-single-strip` in
`infra/perf/pr_scoped_probes.json`, including focused `test_command`,
`coverage_command`, and `probe_command` entries.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux. GitHub Actions remains the merge gate for the
PR-scoped performance report after push.

## Expected metrics

The existing multi-segment metrics should remain neutral to improved. The new
single-value metrics should show lower elapsed time versus the baseline helper
that always calls `split(",")`.