# LoRA Reward Summary Batch Candidate Score Collection

## Goal

Reduce overhead in the LoRA alignment reward summary path by collecting each
sample's candidate scores with a comprehension before extending the aggregate
score list, while preserving candidate group margin and variance semantics.

## Scope

This slice is limited to `worker.model_ops.lora_training_pipeline._reward_summary`.
It does not change training behavior, manifest fields, scoring formulas, or
alignment dataset contracts.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`lora-reward-summary-candidate-minmax` in `infra/perf/pr_scoped_probes.json`.
The entry includes focused `test_command`, `coverage_command`, and
`probe_command` values for:

- `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`
- `services/mlx-worker-python/tests/test_lora_model_ops.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/lora_reward_summary_probe.py`

## Implementation Plan

- Reuse the existing behavior coverage for reward summary percentile, margin,
  and variance calculations.
- Collect per-sample `candidate_scores` with a comprehension and retain the
  existing aggregate `extend` step.
- Keep a scalar candidate count plus running totals, min, and max for group
  metrics.
- Run the registered focused tests, changed-scope coverage, and local registered
  probe on Linux before opening the PR.

## Verification Boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
performance claims are made.

## Success Criteria

- Focused tests pass.
- Changed-scope coverage remains at least 95%.
- The registered probe reports a clear local improvement in `elapsed_ms_mean`.
- GitHub Actions and the PR-scoped performance workflow complete successfully
  before merge.
