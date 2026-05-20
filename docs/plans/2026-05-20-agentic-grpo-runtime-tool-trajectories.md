# Agentic GRPO Runtime Tool Trajectories

## Goal

Implement issue #699 by extending GRPO `runtime_generate` from text-only
candidates to per-candidate multi-turn tool trajectories. This begins
Milestone 2 for the OpenSearch-VL online GRPO/RL rollout direction after the
Milestone 1 reward and rollout manifest contracts landed.

## Scope

- Governed issue: #699.
- Parent direction: #694, OpenSearch-VL alignment: online GRPO/RL rollout for
  tool-use LoRA.
- Milestone issue: #698, online candidate generation and scoring.
- Runtime boundary: Python worker alignment runner.
- Tool boundary: existing deterministic agentic tool runtime and observation
  contract.

## Architecture

The existing `runtime_generate` path loads the policy runtime once and asks it
for multiple candidate responses. Before this slice, the path treated every
candidate as plain text and attached only sample-level tool replay evidence to
the selected policy-update row.

This slice keeps the policy runtime and reward paths unchanged, but changes the
candidate object produced by the runner:

- collect assistant text from `RuntimeTokenEvent` values;
- collect tool calls from `RuntimeToolCallEvent` values;
- parse each tool-call argument fragment as a JSON object;
- execute the generated tool calls through
  `worker.runtime.agentic_tools.execute_agentic_tool_calls`;
- score each candidate with its own executed tool run so tool-efficiency
  components reflect the candidate trajectory;
- project the selected candidate's registry, calls, observations, metrics, and
  turns onto the policy-update row.

Candidate-level reward trace persistence remains the next unit (#700). This
unit records enough candidate-local fields to prove that online generation can
produce and execute multi-turn tool trajectories, while the full candidate
evidence surface remains intentionally narrow.

## Performance And Metrics

The new work only runs the deterministic local tool adapter layer for generated
tool calls. It does not add model loads, network calls, broad filesystem scans,
or additional reward-runtime calls. Tool execution cost is proportional to the
number of generated tool calls and is measured through existing tool metrics:

- `agentic_tool.call_count`
- `agentic_tool.completed_count`
- `agentic_tool.timeout_count`
- `agentic_tool.failed_count`
- `agentic_tool.observation_emitted_bytes`

Success metrics:

- Runtime-generated candidates may include tool calls and per-candidate
  observations.
- The selected policy-update row uses the selected candidate's tool trajectory,
  not sample-level replay copied across the group.
- Tool-efficiency reward components use the candidate-local call count.
- Existing text-only `runtime_generate` behavior remains compatible.
- Changed-line coverage for touched Python files is at least 95 percent.

## Implementation Steps

- [x] Create the issue-specific plan before broad code changes.
- [x] Add a runtime candidate structure that collects text and tool-call
      events from the policy runtime stream.
- [x] Execute generated tool calls through the shared agentic tool runtime.
- [x] Attach the selected candidate trajectory to the policy-update row.
- [x] Add focused tests for runtime-generated tool trajectories.

## Verification

Results:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_rl_alignment_runtime_tool_trajectories.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py::test_mlx_lm_runner_generates_grpo_candidates_with_policy_runtime services/mlx-worker-python/tests/test_lora_model_ops_unit.py::test_mlx_lm_runner_scores_generated_grpo_candidates_with_reward_model
# 4 passed

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py -k 'alignment_rl or grpo or rlhf or reward_model or rollout'
# 25 passed, 110 deselected

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_rl_alignment_runtime_tool_trajectories.py
# 2 passed

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_records_runtime_generated_grpo_evidence services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_supports_rl_alignment_mode_contracts
# 3 passed

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_agentic_grpo_reward_components.py services/mlx-worker-python/tests/test_trajectory_provenance.py::test_alignment_rl_trace_runner_attaches_trajectory_provenance services/mlx-worker-python/tests/test_trajectory_provenance.py::test_alignment_manifest_payload_records_trajectory_provenance_metrics
# 8 passed

git diff --check
# passed

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" COVERAGE_FILE=/tmp/agentic_runtime_tool_trajectories.coverage uv run --frozen --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py -k 'alignment_rl or grpo or rlhf or reward_model or rollout'
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" COVERAGE_FILE=/tmp/agentic_runtime_tool_trajectories.coverage uv run --frozen --project services/mlx-worker-python coverage run --append -m pytest -q services/mlx-worker-python/tests/test_rl_alignment_runtime_tool_trajectories.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" COVERAGE_FILE=/tmp/agentic_runtime_tool_trajectories.coverage uv run --frozen --project services/mlx-worker-python coverage run --append -m pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py -k 'alignment_mode_contracts or runtime_generated_grpo_evidence'
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" COVERAGE_FILE=/tmp/agentic_runtime_tool_trajectories.coverage uv run --frozen --project services/mlx-worker-python coverage run --append -m pytest -q services/mlx-worker-python/tests/test_agentic_grpo_reward_components.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" COVERAGE_FILE=/tmp/agentic_runtime_tool_trajectories.coverage uv run --frozen --project services/mlx-worker-python coverage run --append -m pytest -q services/mlx-worker-python/tests/test_trajectory_provenance.py -k 'alignment_rl_trace_runner or alignment_manifest_payload'
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" COVERAGE_FILE=/tmp/agentic_runtime_tool_trajectories.coverage uv run --frozen --project services/mlx-worker-python coverage json -o /tmp/agentic_runtime_tool_trajectories_coverage.json
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python python scripts/python_changed_line_coverage.py --coverage-json /tmp/agentic_runtime_tool_trajectories_coverage.json --diff-from origin/main services/mlx-worker-python/worker/model_ops/rl_alignment_training.py services/mlx-worker-python/tests/test_rl_alignment_runtime_tool_trajectories.py
# TOTAL 100.00% (121/121)
```

The final pre-commit gate remains pending for the commit.
