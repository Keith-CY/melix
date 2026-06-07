# Report Evidence Lazy Probe Phase Extraction

## Scope

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._report_matrix_roles`.
Most release evidence matrices match via run kinds, metric prefixes, or target fields; only matrices with a `probe_phases` rule need the report-level probe phase set. The current implementation extracts probe phases before checking any rule, so run-kind-only reports still scan `probe_summary` buckets.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values and runs `scripts/report_evidence_gate_run_kind_probe.py` on Linux.

## Plan

1. Preserve release evidence matrix semantics for run-kind, metric-prefix, target-field, and probe-phase rules.
2. Add a focused regression test proving `_report_matrix_roles` does not call `_probe_phases` when the matrix has no probe-phase rules.
3. Lazily compute `_probe_phases(report)` only when a rule declares non-empty `probe_phases`, reusing the computed set for subsequent probe-phase rules.
4. Verify with focused pytest, changed-scope coverage, and the registered probe locally on Linux; use PR-scoped performance CI as the merge gate.

## Metrics

Success is measured by lower `elapsed_ms_mean` / component timings from `scripts/report_evidence_gate_run_kind_probe.py` while preserving the selected component count and focused report-evidence gate behavior.
