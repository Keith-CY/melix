# Evaluation JSON Equal-Value Scoring Fast Path Performance Slice

## Scope

Optimize one Python hot path in `services/mlx-worker-python/worker/productization/evaluation_final_result.py`: `_json_typed_score()` now short-circuits non-dict dict children whose expected and actual values are exactly equal before recursing into list or scalar leaves.

The behavior is unchanged because an exactly equal non-dict JSON child contributes a score of `1.0` whether it is evaluated recursively or accepted directly. Ignored-path handling still runs before the equality check so fully ignored fields keep the existing semantics.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `evaluation-final-result-json-typed-score-aggregate` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- focused tests through `test_command`
- changed-scope coverage through `coverage_command`
- local/CI performance measurement through `probe_command` (`scripts/evaluation_json_typed_score_probe.py`)

## Implementation Plan

1. Preserve ignored-path checks before scoring each dict child.
2. Fetch the actual child value once per key.
3. Return a direct `1.0` contribution for exactly equal expected/actual child values instead of recursing.
4. Verify with focused evaluation final-result tests, changed-scope coverage, and the registered probe on Linux.

## Success Metric

`scripts/evaluation_json_typed_score_probe.py` should report lower `elapsed_ms_mean` for the synthetic wide JSON scoring workload while preserving `score_checksum` and validation behavior.
