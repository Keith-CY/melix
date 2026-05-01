# Benchmark Evaluation Probe Label Fast Path

## Goal

Reduce label-formatting overhead in the benchmark/evaluation report builder while preserving existing metric names and report semantics.

## Scope

This Linux-verifiable Python slice is limited to:

- `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`
- `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`

No Swift, protobuf, dependency, or generated artifact changes are in scope.

## Probe

The affected path is covered by registered PR-scoped probe `benchmark-evaluation-report-running-aggregates` in `infra/perf/pr_scoped_probes.json`. The registered probe already has focused `test_command`, `coverage_command`, and `probe_command` entries.

Tracked metrics:

- `elapsed_ms_mean` (lower is better)
- `peak_bytes_mean` (lower is better)
- `row_count` (parity guard)

## Implementation Plan

1. Add a small `_label_part` helper that keeps numeric probe dimensions on a direct `str(value)` path and only applies space normalization for textual values.
2. Route benchmark and matrix label construction through that helper.
3. Add focused regression coverage for numeric and textual label normalization.
4. Run the focused tests, changed-scope coverage, and registered local probe before opening the PR.

## Validation Boundary

This slice is Python-only and locally validated on Linux. The registered PR-scoped performance workflow remains the merge gate for CI probe validation.
