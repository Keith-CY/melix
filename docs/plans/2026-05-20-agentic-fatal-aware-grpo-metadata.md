# Agentic Fatal-Aware GRPO Metadata

## Goal

Implement issue #702 by adding fatal-state masks and one-sided GRPO advantage
clamp metadata to the alignment RL runner. This starts Milestone 3 of the
OpenSearch-VL online GRPO/RL rollout direction by making fatal candidate
semantics explicit in policy-update evidence before a later optimizer slice
consumes token-level masks.

## Scope

- Governed issue: #702.
- Parent direction: #694, OpenSearch-VL alignment: online GRPO/RL rollout for
  tool-use LoRA.
- Milestone issue: #701, fatal-aware GRPO semantics.
- Runtime boundary: Python worker alignment runner.
- Artifact boundary: `policy_updates.jsonl`, `candidate_reward_traces.jsonl`,
  adapter config, and LoRA alignment run manifest metrics.

## Architecture

Existing GRPO rows already carry reward components and a scalar fatal penalty.
That is not enough for downstream RL consumers to distinguish a merely low
reward from a trajectory whose post-fatal tokens must not receive positive
policy pressure. This slice introduces additive metadata:

- `fatal_aware_grpo_schema_version`: `melix.fatal_aware_grpo.v1`
- `fatal_state_mask`: true when the candidate has a fatal stage.
- `fatal_state_mask_reason`: the fatal stage that caused the mask.
- `grpo_advantage_raw`: candidate reward total minus its group mean.
- `grpo_advantage_clamped`: the advantage after fatal-aware one-sided clamping.
- `grpo_advantage_clamp_applied`: true when a fatal candidate had positive raw
  advantage and the runner clamped it.
- `grpo_advantage_clamp_reason`: `fatal_state_positive_advantage` when clamped.

The v1 clamp policy is deliberately one-sided: fatal candidates may keep zero or
negative advantage so bad trajectories remain penalizable, but positive raw
advantage is clamped to `0.0`. This prevents a fatal trajectory from becoming a
positive policy update when all candidates are weak or when a fatal candidate
otherwise scores above the group mean.

Candidate-local tool timeout or failed observations are fatal states for
runtime-generated candidates. Explicit `candidate.fatal_stage` and
sample-level `fatal_stage` remain supported for scored traces and normalized
datasets.

## Performance And Metrics

The new work is metadata construction over candidates, reward totals, and
candidate-local tool-run metrics that are already in memory. It adds no model
loads, reward-model calls, network calls, tool executions, or broad filesystem
scans. Runtime cost is linear in GRPO candidate count.

Measurement points:

- `fatal_candidate_count`
- `selected_fatal_candidate_count`
- `advantage_clamped_candidate_count`
- existing `candidate_reward_trace_count`
- existing `fatal_trace_count`

Success metrics:

- Every GRPO candidate in scored-trace and runtime-generated paths records
  fatal-aware advantage metadata.
- Fatal candidates have `fatal_state_mask: true` and a stable mask reason.
- Fatal candidates with positive raw advantage have
  `grpo_advantage_clamped == 0.0` and `grpo_advantage_clamp_applied: true`.
- Nonfatal candidates keep raw and clamped advantage equal.
- Adapter config and alignment run metrics expose aggregate fatal/clamp counts.
- Changed-line coverage for touched Python files is at least 95 percent.

## Implementation Steps

- [x] Create the issue-specific plan before broad code changes.
- [x] Add fatal-stage derivation from candidate-local tool timeout/failure
      evidence.
- [x] Add GRPO fatal mask and advantage clamp metadata to scored-trace and
      runtime-generated candidates.
- [x] Surface aggregate fatal/clamp counts in training metrics, adapter config,
      and alignment run manifest metrics.
- [x] Update governing contracts.
- [x] Add focused tests for positive fatal advantage clamping and
      runtime-generated tool failure metadata.

## Verification

Completed commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_agentic_grpo_reward_components.py services/mlx-worker-python/tests/test_rl_alignment_runtime_tool_trajectories.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py -k 'alignment_rl or grpo or rlhf or reward_model or rollout or structured_result'

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_agentic_grpo_reward_components.py services/mlx-worker-python/tests/test_rl_alignment_runtime_tool_trajectories.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py -k 'alignment_rl or grpo or rlhf or reward_model or rollout or structured_result'

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage run --data-file=/tmp/fatal_aware_grpo.coverage -m pytest -q services/mlx-worker-python/tests/test_agentic_grpo_reward_components.py services/mlx-worker-python/tests/test_rl_alignment_runtime_tool_trajectories.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py -k 'alignment_rl or grpo or rlhf or reward_model or rollout or structured_result'
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage json --data-file=/tmp/fatal_aware_grpo.coverage -o /tmp/fatal_aware_grpo_coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json /tmp/fatal_aware_grpo_coverage.json services/mlx-worker-python/worker/model_ops/rl_alignment_training.py services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py services/mlx-worker-python/tests/test_agentic_grpo_reward_components.py services/mlx-worker-python/tests/test_rl_alignment_runtime_tool_trajectories.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py

git diff --check

python3 scripts/pre_commit_gate.py

make swift-test
make py-test
make integration-test
```

After merging latest `origin/main`, final PR-diff coverage was calculated by
reusing `scripts/changed_scope_coverage.py` helpers against
`git diff --unified=0 origin/main...HEAD`. Final PR-scoped performance was
generated by calling `scripts/pre_commit_gate.py` `run_performance_report` with
the `origin/main...HEAD` changed-file list and `base_ref="origin/main"`.

Results:

- Focused GRPO/runtime tests: `10 passed`.
- Wider LoRA alignment subset: `29 passed, 106 deselected`.
- Combined touched Python subset: `38 passed, 107 deselected`.
- Changed-scope coverage: aggregate `99%` (`165` measurable changed lines,
  `1` missed line); touched production files were at or above the 95% gate.
- `git diff --check`: pass.
- Commit-time pre-commit gate before merging latest `origin/main`: Swift tests
  passed, Python tests passed (`2883 passed, 14 skipped`), integration tests
  passed (`114 passed, 1 skipped`).
- Pre-merge pre-commit performance report:
  `.runtime/pre-commit-performance/20260520-112559-28eccf21/report/report.md`.
  Status `ok`; selected direct probes passed with no regressions or
  verification failures.
- After merging latest `origin/main` (`6d9faa88`), combined touched Python
  subset remained `38 passed, 107 deselected`.
- Final PR-diff changed-scope coverage against `origin/main...HEAD`: aggregate
  `99%` (`165` measurable changed lines, `1` missed line); touched production
  files were at or above the 95% gate.
- Final branch `make swift-test`: pass.
- Final branch `make py-test`: `2884 passed, 14 skipped`.
- Final branch `make integration-test`: `114 passed, 1 skipped`.
- Final PR-scoped performance report against `origin/main...HEAD`:
  `.runtime/pre-commit-performance/20260520-121335-e7173501/report/report.md`.
  Status `ok`; two direct/gated probes passed with no regressions or
  verification failures.
