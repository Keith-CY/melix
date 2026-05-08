# Maintenance Matrix Cell Summary Single-Pass Optimization

## Goal

Reduce redundant per-cell work in `MaintenanceCore.run_bench_matrix()` by avoiding an extra `cell_rows` list and the derived `completed_rows` scan when building benchmark matrix summary rows.

## Linux-only constraint

This slice is Python-only and can be verified on Linux with focused pytest, changed-scope coverage, and a local synthetic benchmark-matrix performance probe. It does not change Swift or macOS-only surfaces.

## Touched files

- `services/mlx-worker-python/worker/engine/maintenance_core.py`
- `docs/plans/2026-05-08-maintenance-matrix-cell-summary-single-pass.md`

## Proposed change

Keep the persisted `request_rows` output unchanged, but accumulate per-cell summary values while each request row is produced:

1. Track `completed_count` directly.
2. Append metric values only for completed rows.
3. Derive success/failure counts from `completed_count` and `row_count` instead of building `cell_rows` and filtering it into `completed_rows`.

## Performance probe

Use the existing `maintenance-percentile-vector-reuse` PR-scoped performance probe as the hosted CI gate for this file scope, plus a local synthetic `run_bench_matrix()` probe that compares `origin/main` and this branch on the same fake-runtime matrix workload.

## Success metrics

- Focused benchmark-matrix pytest passes.
- Changed executable coverage is at least 95% for touched Python code.
- Local synthetic probe shows lower mean elapsed time while preserving summary/request row counts and completed counts.
- `git diff --check` passes.
