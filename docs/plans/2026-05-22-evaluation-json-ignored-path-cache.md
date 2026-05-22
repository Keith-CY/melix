# Evaluation JSON Ignored Path Set Cache

## Scope

This Python-only performance slice is limited to final-result JSON scoring in
`services/mlx-worker-python/worker/productization/evaluation_final_result.py`.
The behavior stays equivalent: default ignored paths and profile-level ignored
paths are still applied before recursive typed-score aggregation.

## Registered Probe

The affected path is already covered by the registered PR-scoped probe
`evaluation-final-result-json-typed-score-aggregate` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries that cover:

- `services/mlx-worker-python/worker/productization/evaluation_final_result.py`
- `services/mlx-worker-python/tests/test_evaluation_final_result.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/evaluation_json_typed_score_probe.py`

## Implementation Plan

1. Add a focused regression test proving repeated JSON scoring reuses the
   combined ignored-path set while preserving default and profile ignored paths.
2. Cache the immutable combined ignored-path set by the profile ignored-path
   tuple, avoiding repeated set construction in repeated scoring loops.
3. Run the focused pytest command, changed-scope coverage command, and the
   registered probe locally on Linux before pushing.
4. Use the PR-scoped performance GitHub Actions report as the merge gate.

## Validation Boundary

This slice is pure Python and locally verifiable on Linux. No Swift runtime
performance claim is made.
