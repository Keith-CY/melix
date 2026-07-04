# Report evidence single evidence-id sort elision

## Scope

This Python-only performance slice is limited to release-matrix row rendering in
`worker.productization.report_evidence_gate._release_matrix_rows`.

The existing implementation always sorted each non-empty role evidence-id set
while producing release-matrix rows. Many PR evidence reports map a role to a
single evidence id, where sorting cannot change the result and only adds iterator
and list-sort overhead.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`,
`coverage_command`, and `probe_command` entries and reports
`release_matrix_elapsed_ms_mean` plus the aggregate `elapsed_ms_mean`.

## Optimization hypothesis

Keep multi-evidence roles sorted for deterministic output, but emit a one-item
list directly when a role has exactly one evidence id. This preserves behavior
for empty, single-id, and multi-id roles while reducing release-matrix row
materialization overhead on the common single-id path.

## 2026-07-03 follow-up: single run-kind role fast path

This Python-only follow-up keeps the same registered probe and narrows to
`_report_matrix_roles`. Release-matrix rows commonly use run-kind-only rules with
a single tuple value, so the role scanner can test that tuple directly against the
precomputed report run-kind set instead of dispatching through the general
`_run_kind_rule_matches` helper on every role. Multi-value, non-tuple, and
non-string run-kind rules continue to use the existing general matching behavior.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and the
registered local probe on Linux before opening the PR. GitHub Actions
PR-scoped performance remains the merge gate for the registered probe report.
