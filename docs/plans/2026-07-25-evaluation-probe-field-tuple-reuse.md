# Evaluation Probe Field Tuple Reuse

## Goal

Reduce per-run allocation overhead in the Python evaluation result metrics path by reusing the existing `_SAMPLE_PROBE_MEAN_FIELD_NAMES` tuple when collecting sample probe means.

## Scope

This slice is limited to `EvaluationCore.run_local_suite()` metrics assembly. It does not change evaluation scoring, persistence, dataset selection, or sample probe semantics.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `evaluation-sample-probe-aggregation` in `infra/perf/pr_scoped_probes.json`. The entry watches `services/mlx-worker-python/worker/engine/evaluation_core.py`, focused evaluation tests, PR-scoped performance tests, and includes `test_command`, `coverage_command`, and `probe_command` entries.

## Implementation Plan

1. Keep the existing `_sample_probe_means()` known-field fast path and field-order contract unchanged.
2. Replace the repeated tuple comprehension at the run metrics call site with the precomputed `_SAMPLE_PROBE_MEAN_FIELD_NAMES` constant.
3. Verify behavior with focused evaluation tests, changed-scope coverage, and the registered local probe on Linux.

## Metrics

Primary metric: `evaluation-sample-probe-aggregation` `elapsed_ms_mean` and `per_call_ms_mean` (lower is better). The expected improvement is small but should remove one tuple allocation and element copy per local evaluation run.
