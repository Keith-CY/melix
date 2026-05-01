# Evaluation Core Single-Pass Summary Plan

## Goal

Reduce redundant post-processing work in `services/mlx-worker-python/worker/engine/evaluation_core.py` by collapsing repeated summary scans over local evaluation samples into one deterministic pass while preserving result metrics and persisted output shapes.

## Linux-only constraint

This cron run executes on Linux, so the slice must stay inside the Python worker and use local Python verification plus Melix PR-scoped performance CI.

## Touched files

- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/tests/test_evaluation_core.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Optimization hypothesis

`EvaluationCore.run_local_suite()` currently rescans `sample_records` multiple times to compute typed-score mean, extraction/validation counts, threshold pass rate, and code-exec counts before also calling `_sample_probe_means(...)`. A single accumulator pass plus the existing probe-mean helper should reduce Python-loop overhead for larger suites without changing user-visible metrics.

## Probe definition

Use the existing `evaluation-sample-probe-aggregation` PR-scoped probe, updated so it measures the full local-suite summary path instead of only `_sample_probe_means(...)`.

Success metric:
- lower `elapsed_ms_mean` for the scoped probe versus `origin/main`
- unchanged reported sample count / semantic summary outputs

## Verification

1. Focused failing test first for the new single-pass summary helper / behavior.
2. Focused pytest for evaluation core and scoped-probe tests.
3. Changed-scope coverage via `coverage json` + `scripts/changed_scope_coverage.py` with a >=95% gate.
4. Explicit local performance probe using the updated `evaluation-sample-probe-aggregation` implementation.
5. `git diff --check`.
