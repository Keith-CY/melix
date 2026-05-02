# Benchmark Evaluation Flat Aggregate Map

## Goal

Reduce hot-path dictionary churn in `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py` by replacing nested per-label aggregate maps with a flatter aggregate structure while preserving report metric names, values, and warning semantics.

## Scope

This Linux-verifiable Python optimization slice is limited to:

- `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`
- `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`

No Swift, protobuf, workflow, dependency, or generated-artifact changes are in scope.

## Performance Probe

Use the already-registered PR-scoped performance probe `benchmark-evaluation-report-running-aggregates` from `infra/perf/pr_scoped_probes.json`.

Tracked metrics:

- `elapsed_ms_mean` — lower is better
- `peak_bytes_mean` — lower is better
- `row_count` — parity guard

## Success Metrics

- Focused pytest for `test_benchmark_evaluation_report.py` passes.
- Changed-scope automated coverage for the touched executable Python file is at least 95%.
- The local probe reports identical `row_count` and non-regressing `elapsed_ms_mean` and `peak_bytes_mean` versus the pre-change baseline.

## Implementation Plan

1. Add a focused regression test that locks the flat aggregate helper behavior and preserves exported metric names and values.
2. Replace nested `label -> key -> aggregate` updates in `_collect_benchmark_probe_metrics(...)` with a flat aggregate map keyed by `(label, key)`.
3. Finalize the flat aggregate map back into the existing `metrics[f"{prefix}.{label}.{key}_{suffix}"]` contract.
4. Run focused pytest, changed-scope coverage, `git diff --check`, and the registered local performance probe before commit.

## Validation Boundary

This is a Python-only Linux-local optimization slice. The existing PR-scoped performance CI probe for this path remains the CI merge gate after the PR is opened.
