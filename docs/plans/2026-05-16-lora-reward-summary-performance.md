# LoRA Reward Summary Candidate Hot-Loop Bindings

## Scope

This slice covers `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py` and the registered PR-scoped probe `lora-reward-summary-candidate-minmax`.

## Optimization

`_reward_summary` performs a tight loop over LoRA alignment reward samples and candidate groups. It already avoids repeated `sum()`, `min()`, and `max()` passes by maintaining candidate group totals, square totals, min, and max in one pass.

This slice keeps that behavior and binds the hot helpers used inside the reward-summary loop:

- list `append`/`extend` methods used for score and margin accumulation
- `float`, `isinstance`, `dict`, and `list` lookups used for candidate validation and score conversion

This reduces repeated global/builtin and method lookup overhead in the inner candidate loop without changing the summary algorithm or output schema.

Behavior remains unchanged:

- all reward and candidate scores still participate in `reward_mean`, `reward_p50`, and `reward_p95`
- candidate group margin and variance still use the same per-group min, max, total, square total, and count
- non-dict candidates and candidates without `score` remain ignored

A rejected experiment in this slice streamed candidate scores directly into the global score vector to remove the per-sample candidate list, but the registered local probe regressed from about 47.2 ms to 49-52 ms. The accepted change keeps the existing per-group list and only binds hot helpers.

## Validation

Use the registered probe entry in `infra/perf/pr_scoped_probes.json`:

- focused LoRA alignment tests from `test_command`
- changed-scope coverage from `coverage_command`
- `scripts/lora_reward_summary_probe.py` from `probe_command`

The Linux local run validates Python behavior and probe metrics for this slice.
