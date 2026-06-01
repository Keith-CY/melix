# Report evidence target-field disjoint slice

## Scope

Optimize the Python report-evidence release-matrix target-field rule matcher without changing gate semantics.

The slice is intentionally limited to `worker.productization.report_evidence_gate._rule_matches_report` and its focused unit/performance coverage.

## Registered probe

The affected path is covered by the existing PR-scoped performance probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- `test_command` for `test_report_evidence_gate.py` and PR-scoped probe selection/script tests.
- `coverage_command` for changed-scope coverage over the gate module, tests, probe script, and registry.
- `probe_command` running `scripts/report_evidence_gate_run_kind_probe.py`.

## Optimization

Target-field rules used to iterate every field/value pair in every target row before checking membership in the configured target-field set. Most rows in the release-matrix scan are unrelated, so the matcher now performs a C-level `frozenset.isdisjoint(target)` key check first and only reads values from rows that contain at least one candidate target field.

## Success metrics

Accept only if the registered local probe remains behaviorally green and reports lower `target_field_elapsed_ms_mean` with no regression in focused tests/coverage.
