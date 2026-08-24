# Report evidence run-kind set comprehension

## Scope

This Python-only performance slice is limited to `_report_run_kind_values()` in
`services/mlx-worker-python/worker/productization/report_evidence_gate.py`.
The function builds the normalized run-kind set once per report before release
matrix role matching.

## Registered performance probe

The affected path is covered by the registered PR-scoped performance probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`. This slice extends that registry entry to
watch this plan and include the focused regression test for the run-kind value
normalization fast path. The entry already provides focused `test_command`,
`coverage_command`, and `probe_command` entries and reports
`run_kind_elapsed_ms_mean` plus the aggregate report-evidence gate metrics.

## Implementation plan

1. Preserve the exact-string fast path and non-string/string-subclass
   normalization behavior with a focused unit test.
2. Replace the manual `set.add` loop with a set comprehension so CPython can
   build the run-kind value set with less per-row loop overhead.
3. Run the registered focused tests, changed-scope coverage, and registered probe
   locally on Linux before opening the PR.
4. Use the PR-scoped performance workflow as the CI merge gate.

## Success criteria

- Focused report evidence gate tests pass locally.
- Changed-scope coverage remains at or above the repository threshold.
- The registered local and CI probe show no in-scope regression, with the primary
  target being lower `run_kind_elapsed_ms_mean`.
