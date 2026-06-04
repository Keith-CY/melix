# Report Evidence Matrix Single-Role Fast Path

## Scope

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._release_matrix_rows`.
The common PR evidence path stores one cached release-matrix role per analyzed report, so the function can avoid the generic multi-role tuple materialization path for single-role rows.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values and runs `scripts/report_evidence_gate_run_kind_probe.py`.

## Plan

1. Preserve the existing multi-role behavior and evidence-id stringification semantics.
2. Add a focused regression test for the single-role release-matrix path.
3. Implement a single-role fast path that updates the per-role evidence set directly and falls back to the existing generic path for multi-role rows.
4. Verify with focused pytest, changed-scope coverage, and the registered probe locally on Linux; use PR-scoped performance CI as the merge gate.

## Metrics

Success is measured by `release_matrix_elapsed_ms_mean` from `scripts/report_evidence_gate_run_kind_probe.py`; behavior parity is measured by focused report-evidence gate tests and changed-scope coverage for the touched module and tests.
