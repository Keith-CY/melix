# Training Token Stats Prompt/Completion Fast Path

## Goal

Reduce per-sample overhead in the Python training dataset token-statistics path while preserving the existing whitespace token estimator, percentile semantics, and manifest/report payload shape.

## Scope

- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `services/mlx-worker-python/tests/test_training_dataset_builder.py`

## Registered probe

The affected path is covered by the registered PR-scoped probe `training-dataset-token-percentiles-single-sort` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and measures `elapsed_ms_mean` for `_build_token_stats()` over 20,000 prompt/completion samples.

## Implementation plan

1. Keep token count collection behavior unchanged.
2. Keep the direct `prompt_completion` branch in `_collect_token_stats()` so the common training-dataset path avoids dispatching through the generic format helper for every sample.
3. Collect prompt/completion token series with list-comprehension fast paths and inline the unchanged whitespace split count for that hot branch, avoiding an extra list copy for already-materialized sample lists while preserving one-shot iterable support and percentile semantics.
4. Reuse prompt/completion/total token sums captured during the single collection loop so the summary step does not rescan each token list just to compute means.
5. Preserve the generic helper path for chat and text-completion formats.
6. Keep focused regression coverage that fails if the prompt/completion path falls back to the generic helper, consumes the iterable more than once, or recomputes means by summing token lists after collection.
7. Validate with the focused training dataset tests, changed-scope coverage, and the registered PR-scoped performance probe on Linux.

## Success criteria

- Focused training dataset tests pass.
- Changed-scope coverage for the touched Python worker files is at least 95%.
- The registered probe reports a stable `elapsed_ms_mean` improvement or a clearly non-regressive result.
