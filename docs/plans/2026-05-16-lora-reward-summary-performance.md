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

The 2026-06-12 follow-up re-tested candidate-score streaming with the now-registered `lora-reward-summary-candidate-minmax` probe. The accepted slice removes the per-sample `candidate_scores` list, appends valid candidate scores directly into the global score vector, and preserves the existing one-pass per-group min, max, total, and square-total calculation. The focused Linux probe improved from `elapsed_ms_mean=44.906307` ms to `39.305011` ms for the 5k-sample / 32-candidate workload.

## Validation

Use the registered probe entry in `infra/perf/pr_scoped_probes.json`:

- focused LoRA alignment tests from `test_command`
- changed-scope coverage from `coverage_command`
- `scripts/lora_reward_summary_probe.py` from `probe_command`

The Linux local run validates Python behavior and probe metrics for this slice.
