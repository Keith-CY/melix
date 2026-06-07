# Report Evidence Gate Run-Kind Set Reuse

## Summary

This Python performance slice narrows the report evidence gate release-matrix
role lookup. Run-kind-only matrix rules now reuse one normalized set of observed
report run kinds instead of scanning the same `runs` rows once per role.

## Scope

- Affected production path: `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- Focused tests: `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- Registered PR-scoped probe: `report-evidence-gate-run-kind-set-membership`

## Probe Contract

The registered probe already covers the affected path in
`infra/perf/pr_scoped_probes.json` and includes focused `test_command`,
`coverage_command`, and `probe_command` entries. This slice uses the existing
probe because it measures `_report_matrix_roles()` and `_rule_matches_report()`
with large synthetic run-kind, metric-prefix, target-field, release-matrix, and
slowest-phase inputs.

## Verification Plan

Run the registered focused pytest command, changed-scope coverage command, and
probe locally on Linux before pushing. The GitHub PR-scoped performance workflow
remains the merge gate and must complete successfully before squash merge.
