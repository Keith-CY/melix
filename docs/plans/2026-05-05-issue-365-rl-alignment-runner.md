# Issue 365 RL Alignment Runner Slice

## Goal

Continue the implementation path for
https://github.com/Keith-CY/melix/issues/365 by adding a concrete worker runner
for scored GRPO and RLHF alignment datasets, plus an opt-in runtime-backed GRPO
candidate-generation path.

Issue 365 is still not complete after this slice. This work turns the existing
GRPO/RLHF contracts, dataset validation, candidate traces, and alignment
manifests into executable scored-trace policy-update jobs. It also allows GRPO
to load the current policy runtime and generate candidate responses when
`candidate_generation_mode=runtime_generate`. That runtime path records generated
candidates, runtime backend identity, seed-overlap proxy scores, and policy
update traces. It does not yet claim final reward-model scoring, PPO/GRPO
gradient updates through MLX-LM, or release readiness.

## Scope

### Included

- Route `training_objective=alignment_rl` through a dedicated worker-side runner.
- Support `grpo` from `prompt_candidate` datasets with scored candidate groups.
- Support opt-in GRPO runtime candidate generation from the current policy
  runtime with `candidate_generation_mode=runtime_generate`.
- Record runtime generation/scoring evidence in adapter config, policy-update
  traces, training metrics, and `melix.alignment_run.v1`.
- Support `rlhf` from `reward_scored` datasets with an existing reward model
  manifest reference.
- Produce adapter weights/config artifacts and checkpoint lineage for scored
  RL-style alignment jobs.
- Record policy-update metrics derived from scored samples, including reward
  mean/percentiles, candidate group margin/variance, update count, selected
  candidate count, KL penalty, and reward-model lineage where applicable.
- Keep final acceptance honest by marking scored-trace execution as
  deterministic and runtime generation as runtime-generated scored-trace
  execution, not as reward-model-backed PPO.

### Excluded

- Local reward-model inference and reward scoring from issue 366.
- PPO/GRPO gradient updates through MLX-LM.
- End-to-end real local runtime release evidence.
- Window UI acceptance.
- Closing issue 365.

## Performance And Metrics

This slice reads the normalized `train.jsonl` once and writes small adapter,
config, and checkpoint artifacts. The default scored-trace runner is
deterministic and does not load the base model. The opt-in
`runtime_generate` GRPO path loads the policy runtime once per job and generates
`grpo_candidate_count` candidates per prompt.

Success metrics:

- GRPO/RLHF jobs run through the default worker runner instead of failing with
  `unsupported_alignment_trainer`.
- GRPO jobs can opt into runtime-backed candidate generation and record
  generated-candidate evidence without being marked release-ready.
- Alignment manifests include scored policy-update metrics.
- Adapter manifests preserve alignment backlinks and checkpoint lineage.
- Changed-scope coverage remains at least 95 percent.

## Verification

Targeted commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py services/mlx-worker-python/tests/test_training_dataset_builder.py
git diff --check
```

Coverage and metrics:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py services/mlx-worker-python/tests/test_training_dataset_builder.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /tmp/issue365-rl-alignment-runner-coverage.json
python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-rl-alignment-runner-coverage.json --diff-from origin/main services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py services/mlx-worker-python/worker/model_ops/rl_alignment_training.py services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py docs/plans/2026-05-05-issue-365-rl-alignment-runner.md
```

Results on 2026-05-05 before runtime-generation extension:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py services/mlx-worker-python/tests/test_training_dataset_builder.py`: 194 passed, 9 skipped.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py services/mlx-worker-python/tests/test_training_dataset_builder.py`: 194 passed, 9 skipped.
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-rl-alignment-runner-coverage.json --diff-from origin/main services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py services/mlx-worker-python/worker/model_ops/rl_alignment_training.py services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py docs/plans/2026-05-05-issue-365-rl-alignment-runner.md`: 100.00% total changed-line coverage (235/235).
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python python -m compileall -q services/mlx-worker-python/worker/model_ops/rl_alignment_training.py services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py`: passed.
- `git diff --check`: passed.

Results on 2026-05-05 after runtime-generation extension:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py services/mlx-worker-python/tests/test_training_dataset_builder.py`: 201 passed, 9 skipped.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py services/mlx-worker-python/tests/test_training_dataset_builder.py`: 201 passed, 9 skipped.
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-rl-alignment-runner-coverage.json --diff-from origin/main services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py services/mlx-worker-python/worker/model_ops/rl_alignment_training.py services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py services/mlx-worker-python/worker/model_ops/training_config.py services/mlx-worker-python/worker/engine/maintenance_core.py services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py docs/plans/2026-05-05-issue-365-rl-alignment-runner.md`: 98.52% total changed-line coverage (465/472).
- `python3 -m compileall -q services/mlx-worker-python/worker/model_ops/rl_alignment_training.py services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py services/mlx-worker-python/worker/model_ops/training_config.py services/mlx-worker-python/worker/engine/maintenance_core.py services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py`: passed.
- `git diff --check`: passed.

## Remaining Issue 365 Gaps

- Reward-model local inference and PPO/RL updates from issue 366.
- Real reward-model scoring for GRPO generated candidates.
- PTQ/QAT real local inference release evidence.
- Full CLI chain tests for every business line.
- Window UI runnable and inspectable acceptance for every business line.
- Final release evidence separating deterministic/unit evidence from real local
  runtime evidence.
