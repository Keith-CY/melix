# Training Token Hot-Loop Get Binding

## Goal

Reduce Python attribute-lookup overhead in the prompt/completion training-token statistics hot loop while preserving the existing whitespace token estimator, quality counters, percentile semantics, and manifest/report payload shape.

## Scope

- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `infra/perf/pr_scoped_probes.json` (command normalization only: use `python3` for the registered probe command)
- `docs/plans/2026-05-21-training-token-hot-loop-get-binding.md`

## Registered Probe

The affected path is already covered by the registered PR-scoped probe `training-dataset-token-percentiles-single-sort` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries for the training dataset builder and PR-scoped performance tests. It measures:

- `elapsed_ms_mean` (lower is better)
- `peak_bytes_mean` (lower is better)

## Implementation Plan

1. Keep the direct `prompt_completion` token collection path and all token-count semantics unchanged.
2. Bind `sample.get` once per hot-loop row before reading `prompt` and `completion`, avoiding repeated bound-method lookup while preserving non-dict sample assumptions already enforced by callers.
3. Normalize the registered probe command from `python` to `python3` without changing probe behavior.
4. Verify locally on Linux with focused tests, changed-scope coverage, and the registered PR-scoped performance probe against `origin/main`.

## Success Criteria

- Focused tests and changed-scope coverage pass.
- The registered local probe is non-regressive or improved for `elapsed_ms_mean` with unchanged `sample_count`, `duplicate_count`, and `dirty_count`.
- CI PR-scoped performance completes successfully before merge.
