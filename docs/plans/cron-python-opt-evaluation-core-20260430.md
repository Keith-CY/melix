# EvaluationCore Redundant Copy Reduction Plan

## Scope
- Repository slice: `services/mlx-worker-python`
- Target file: `worker/engine/evaluation_core.py`
- Verification target: Linux-local pytest and coverage only

## Goal
Reduce redundant list copying and repeated metric scans in `EvaluationCore` without changing public behavior.

## Proposed changes
1. Avoid copying the full dataset sample list in `_plan_evaluation_samples()` when `seed <= 0`.
2. Reuse one combined sample list for dataset validation calls inside `run_local_suite()` instead of rebuilding the same list twice.
3. Aggregate sample probe means in one pass instead of rescanning `sample_records` once per metric field.

## Tests
1. Keep the existing streaming dataset tests passing.
2. Add a deterministic test for `_plan_evaluation_samples()` with `seed=0` and negative bounds.
3. Add a probe-metric aggregation test to confirm the optimized metrics remain identical.

## Performance probe
- Run a small Python benchmark that compares:
  - old-style repeated probe mean scans vs new single-pass aggregation
  - old-style unconditional list copy vs conditional copy for `seed=0`
- Record concrete timing and peak-memory numbers in the PR.
