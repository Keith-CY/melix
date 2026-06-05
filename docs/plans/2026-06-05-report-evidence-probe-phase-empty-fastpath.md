# Report Evidence Probe Phase Empty Fast Path

## Scope

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._rule_matches_report`.
Most release evidence matrix rules match through run kinds, metric prefixes, or target fields and do not declare `probe_phases`; the fallback probe-phase check should not normalize an empty default rule on those non-match paths.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values and runs `scripts/report_evidence_gate_run_kind_probe.py`.

## Plan

1. Preserve existing release evidence matrix matching semantics for run-kind, metric-prefix, target-field, and non-empty probe-phase rules.
2. Add a focused regression test proving empty or absent probe-phase rules skip set normalization.
3. Implement the fast path by returning `False` before `_string_frozenset` when the probe-phase rule is empty.
4. Verify with focused pytest, changed-scope coverage, and the registered probe locally on Linux; use PR-scoped performance CI as the merge gate.

## Metrics

Success is measured by `elapsed_ms_mean` and the component timings from `scripts/report_evidence_gate_run_kind_probe.py`; behavior parity is measured by focused report-evidence gate tests and changed-scope coverage for the touched module and tests.
