# Agentic GRPO Reward Components

## Goal

Implement issue #696 by defining the first executable Melix contract for
agentic GRPO reward components. The slice keeps the current deterministic
scored-trace and reward-model paths compatible while making each policy-update
trace expose the component scores that future online rollout and fatal-aware
GRPO slices will consume.

## Scope

- Governed issue: #696.
- Parent direction: #694, OpenSearch-VL alignment: online GRPO/RL rollout for
  tool-use LoRA.
- Runtime boundary: Python worker alignment trace construction in
  `worker.model_ops.rl_alignment_training`.
- Artifact boundary: `policy_updates.jsonl` rows and alignment run metrics.

## Architecture

Melix already has a scalar reward path for GRPO and RLHF. This slice adds a
structured component projection at the same boundary where scalar rewards enter
policy-update evidence:

- `final_answer`: correctness or reward-model quality signal.
- `tool_efficiency`: positive when tool use stays within the budget implied by
  the sample or fixture; negative when a trace exceeds it.
- `format`: parser and response-format validity signal.
- `fatal_failure`: penalty applied when a sample or candidate is associated with
  a fatal stage.
- `total`: canonical scalar value consumed by the current deterministic trainer.

The component projection is intentionally additive. Existing scalar fields such
as `selected_reward`, `reward_mean`, and candidate scores remain stable. Future
fatal-aware GRPO work can replace the simple fatal penalty and advantage
handling without changing the artifact names introduced here.

## Performance And Metrics

This is metadata construction over the in-memory sample and candidate rows
already loaded for alignment training. It does not add model execution, broad
filesystem scans, network calls, or extra runtime invocations.

Success metrics:

- Every selected GRPO and RLHF policy-update row includes `reward_components`.
- GRPO candidate rows include component scores for each candidate.
- Fatal samples record `fatal_stage`, `fatal_penalty_applied`, and a negative
  `fatal_failure` component.
- Alignment metrics report component means and fatal counts.
- Changed-line coverage for touched Python files is at least 95 percent.

## Implementation Steps

- [x] Update the trajectory contract to name the GRPO component keys consumed by
      issue #696.
- [x] Add a worker helper that normalizes reward components from sample,
      candidate, scalar score, tool-run metrics, and fatal stage.
- [x] Attach component evidence to scored-trace GRPO, runtime-generated GRPO,
      and RLHF trace rows.
- [x] Add focused unit tests for component totals, fatal penalties, and
      alignment metrics.
- [x] Run focused tests, changed-line coverage, `git diff --check`, and the
      repository pre-commit gate before opening the PR.

## Verification

Results:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_agentic_grpo_reward_components.py
# 5 passed

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py::test_write_normalized_dataset_snapshot_applies_manifest_overrides services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_training_dataset_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
# 3 passed

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py -k 'grpo or rlhf or reward_model or alignment_rl'
# 25 passed, 110 deselected

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage run --data-file=/tmp/agentic_grpo_reward_components.coverage -m pytest -q services/mlx-worker-python/tests/test_agentic_grpo_reward_components.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage run --append --data-file=/tmp/agentic_grpo_reward_components.coverage -m pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py::test_write_normalized_dataset_snapshot_applies_manifest_overrides
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage run --append --data-file=/tmp/agentic_grpo_reward_components.coverage -m pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py -k 'grpo or rlhf or reward_model or alignment_rl'
# 5 passed; 1 passed; 25 passed, 110 deselected

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage json --data-file=/tmp/agentic_grpo_reward_components.coverage -o /tmp/agentic_grpo_reward_components_coverage.json
# wrote JSON report

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python python scripts/python_changed_line_coverage.py --coverage-json /tmp/agentic_grpo_reward_components_coverage.json services/mlx-worker-python/worker/model_ops/rl_alignment_training.py services/mlx-worker-python/worker/model_ops/training_dataset.py services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py services/mlx-worker-python/tests/test_agentic_grpo_reward_components.py services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py
# Final changed-line coverage command included all touched Python files:
# services/mlx-worker-python/worker/model_ops/rl_alignment_training.py: 100.00% (86/86)
# services/mlx-worker-python/worker/model_ops/training_dataset.py: 100.00% (16/16)
# services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py: 100.00% (6/6)
# services/mlx-worker-python/tests/test_training_dataset_builder.py: 100.00% (25/25)
# TOTAL 100.00% (133/133)

git diff --check
# passed

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py
# 135 passed, 2 warnings
```
