# Report Evidence Run Kind Normalization Fast Path

Date: 2026-08-13

## Scope

This Python-only performance slice is limited to `_report_run_kind_values()` in
`services/mlx-worker-python/worker/productization/report_evidence_gate.py`.

## Problem

Release evidence matrix matching derives the report `run_kind` set once before
checking matrix rules. The current set comprehension always calls `str(...)` for
every row, even though the normal report payload path already stores run kinds as
plain strings. The registered probe measures run-kind matching and matrix role
selection, so avoiding unnecessary string conversion on exact-string values is a
small measurable slice.

## Plan

- Keep the returned `set[str]` contract and non-string stringification behavior.
- Replace the comprehension with a single explicit loop that binds `set.add`.
- Use exact-string values directly and fall back to `str(...)` for non-string
  values.
- Use the existing registered PR-scoped probe
  `report-evidence-gate-run-kind-set-membership` for tests, coverage, and
  metrics.

## Registered Probe

Registered PR-scoped probe: `report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`.

The probe covers `report_evidence_gate.py`, focused report-evidence tests,
`test_pr_scoped_performance.py`, and `scripts/report_evidence_gate_run_kind_probe.py`
with `test_command`, `coverage_command`, and `probe_command` entries. It reports
`run_kind_elapsed_ms_mean`, `matrix_roles_elapsed_ms_mean`, and release-matrix
metrics in addition to the aggregate `elapsed_ms_mean`.

## Acceptance Criteria

- Focused report evidence gate tests pass locally on Linux.
- Changed-scope coverage is at least 95% for the touched scope.
- The registered local probe reports neutral-to-improved run-kind and matrix-role
  metrics against `origin/main`.
- GitHub Actions PR-scoped performance completes successfully before merge.
