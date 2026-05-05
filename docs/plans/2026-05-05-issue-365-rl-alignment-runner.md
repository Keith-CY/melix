# Issue 365 RL Alignment Runner Slice

## Goal

Continue the implementation path for
https://github.com/Keith-CY/melix/issues/365 by adding a concrete worker runner
for scored GRPO and RLHF alignment datasets, plus opt-in runtime-backed GRPO
candidate generation and reward-runtime scoring paths.

Issue 365 is still not complete after this slice. This work turns the existing
GRPO/RLHF contracts, dataset validation, candidate traces, and alignment
manifests into executable scored-trace policy-update jobs. It also allows GRPO
to load the current policy runtime and generate candidate responses when
`candidate_generation_mode=runtime_generate`. That runtime path records generated
candidates, runtime backend identity, seed-overlap proxy scores, and policy
update traces. A follow-up extension in this branch allows
`candidate_scoring_mode=reward_model` to load a reward runtime once per job and
score GRPO candidates or RLHF responses through the reward runtime interface.
It does not yet claim PPO/GRPO gradient updates through MLX-LM or release
readiness.

## Scope

### Included

- Route `training_objective=alignment_rl` through a dedicated worker-side runner.
- Support `grpo` from `prompt_candidate` datasets with scored candidate groups.
- Support opt-in GRPO runtime candidate generation from the current policy
  runtime with `candidate_generation_mode=runtime_generate`.
- Record runtime generation/scoring evidence in adapter config, policy-update
  traces, training metrics, and `melix.alignment_run.v1`.
- Support explicit `candidate_scoring_mode=reward_model` for GRPO/RLHF when a
  reward runtime and readable reward-model manifest are provided.
- Support `rlhf` from `reward_scored` datasets with an existing reward model
  manifest reference.
- Produce adapter weights/config artifacts and checkpoint lineage for scored
  RL-style alignment jobs.
- Record policy-update metrics derived from scored samples, including reward
  mean/percentiles, candidate group margin/variance, update count, selected
  candidate count, KL penalty, and reward-model lineage where applicable.
- Keep final acceptance honest by marking scored-trace execution as
  deterministic and runtime generation as runtime-generated scored-trace
  execution, and reward-model scoring as reward-runtime scored-trace execution,
  not as reward-model-backed PPO.

### Excluded

- Reward-model training and standalone reward-model artifact generation from
  issue 366.
- PPO/GRPO gradient updates through MLX-LM.
- End-to-end real local runtime release evidence.
- Window UI acceptance.
- Closing issue 365.

## Performance And Metrics

This slice reads the normalized `train.jsonl` once and writes small adapter,
config, and checkpoint artifacts. The default scored-trace runner is
deterministic and does not load the base model. The opt-in
`runtime_generate` GRPO path loads the policy runtime once per job and generates
`grpo_candidate_count` candidates per prompt. The opt-in
`candidate_scoring_mode=reward_model` path loads the reward runtime once per job
and scores one response per RLHF row or one generated/trace candidate per GRPO
candidate.

Success metrics:

- GRPO/RLHF jobs run through the default worker runner instead of failing with
  `unsupported_alignment_trainer`.
- GRPO jobs can opt into runtime-backed candidate generation and record
  generated-candidate evidence without being marked release-ready.
- GRPO/RLHF jobs can opt into reward-runtime scoring and record reward model
  backend, reward model id, and per-response score evidence.
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
python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-rl-alignment-runner-coverage.json --diff-from origin/main services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py services/mlx-worker-python/worker/model_ops/rl_alignment_training.py services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py services/mlx-worker-python/worker/model_ops/training_config.py services/mlx-worker-python/worker/runtime/mlx_text_runtime.py services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py docs/plans/2026-05-05-issue-365-rl-alignment-runner.md
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

Results on 2026-05-05 after reward-runtime scoring extension:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py services/mlx-worker-python/tests/test_training_dataset_builder.py`: 209 passed, 9 skipped.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py services/mlx-worker-python/tests/test_training_dataset_builder.py`: 209 passed, 9 skipped.
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-rl-alignment-runner-coverage.json --diff-from origin/main services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py services/mlx-worker-python/worker/model_ops/rl_alignment_training.py services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py services/mlx-worker-python/worker/model_ops/training_config.py services/mlx-worker-python/worker/runtime/mlx_text_runtime.py services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py docs/plans/2026-05-05-issue-365-rl-alignment-runner.md`: 96.53% total changed-line coverage (779/807).
- `python3 -m compileall -q services/mlx-worker-python/worker/model_ops/rl_alignment_training.py services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py services/mlx-worker-python/worker/model_ops/training_config.py services/mlx-worker-python/worker/runtime/mlx_text_runtime.py services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py`: passed.
- `git diff --check`: passed.

## Remaining Issue 365 Gaps

- Reward-model training and PPO/RL policy updates from issue 366.
- Real local-runtime release evidence for reward-model scoring outside the
  scripted reward-runtime tests.
- PTQ/QAT real local inference release evidence.
- Full CLI chain tests for every business line.
- Window UI runnable and inspectable acceptance for every business line.
- Final release evidence separating deterministic/unit evidence from real local
  runtime evidence.
