# LoRA reward summary in-place sort performance slice

## Scope

This Python-only performance slice is limited to the LoRA reward summary helper in
`services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`.

The helper already computes reward totals, candidate group margins, and variance
in one pass. The remaining allocation point is percentile preparation: the helper
uses `sorted(...)` to build copied ordered lists for reward scores and candidate
margins even though those local accumulators are not reused afterward.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`lora-reward-summary-candidate-minmax` in `infra/perf/pr_scoped_probes.json`.
The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries and measures:

- `elapsed_ms_mean` (lower is better)
- `sorted_calls_mean` (lower is better)

## Implementation Plan

1. Keep the existing single-pass score and candidate margin accumulation.
2. Replace copied `sorted(...)` calls with in-place `.sort()` on local accumulator
   lists immediately before percentile calculation.
3. Preserve percentile outputs and existing invalid-candidate handling.
4. Keep tests focused on the registered probe path and verify the registered
   probe locally on Linux.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py::test_alignment_percentile_uses_interpolation_and_upper_bound services/mlx-worker-python/tests/test_lora_model_ops.py::test_reward_summary_reuses_candidate_group_minmax services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_supports_rl_alignment_mode_contracts services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_supports_qlora_with_hf_valid_split_and_persists_desired_alias services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_lora_reward_summary_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_lora_reward_summary_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_lora_reward_summary_probe_script_main_covers_checked_in_file
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py::test_alignment_percentile_uses_interpolation_and_upper_bound services/mlx-worker-python/tests/test_lora_model_ops.py::test_reward_summary_reuses_candidate_group_minmax services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_supports_rl_alignment_mode_contracts services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_supports_qlora_with_hf_valid_split_and_persists_desired_alias services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_lora_reward_summary_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_lora_reward_summary_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_lora_reward_summary_probe_script_main_covers_checked_in_file && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/lora_reward_summary_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/lora_reward_summary_probe.py
```

## 2026-07-18 follow-up slice: percentile helper and length reuse

This follow-up Python-only slice keeps the same registered
`lora-reward-summary-candidate-minmax` probe and remains limited to
`_reward_summary(...)`. The helper now binds `_percentile_value(...)` once before
constructing the summary and reuses the score list length after the in-place
sort. This preserves reward summary semantics while reducing repeated helper and
length lookups in the registered large-candidate workload.

## 2026-08-20 follow-up slice: candidate total branch elision

This follow-up Python-only slice keeps the same registered
`lora-reward-summary-candidate-minmax` probe and remains limited to
`_reward_summary(...)`. The helper now always folds the per-sample
`candidate_score_total` into the aggregate reward total after scanning the
candidate group. Samples without valid candidate scores add `0.0`, preserving
all summary semantics while removing one hot-loop branch from the registered
large-candidate workload.

## Acceptance Criteria

- Focused tests pass.
- Changed-scope coverage is at least 95%.
- Registered probe keeps `sorted_calls_mean == 0` and shows no elapsed regression.
