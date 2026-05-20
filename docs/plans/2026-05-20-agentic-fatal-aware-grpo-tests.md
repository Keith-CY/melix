# Agentic Fatal-Aware GRPO Test Coverage

## Goal

Implement issue #703 by strengthening tests for Milestone 3 fatal-aware GRPO
semantics after the metadata slice landed in #702.

## Scope

- Governed issue: #703.
- Parent milestone: #701, fatal-aware GRPO semantics.
- Parent direction: #694, OpenSearch-VL alignment online GRPO/RL rollout for
  tool-use LoRA.
- Runtime boundary: Python worker alignment runner tests only.

## Coverage Targets

Existing tests cover positive fatal advantage clamping and runtime timeout
metadata for a selected fatal candidate. This slice adds tests for the remaining
contract edge cases:

- Fatal candidates with negative raw advantage stay tracked and penalized, but
  are not clamped.
- A fatal candidate can lose selection because the fatal penalty lowers its
  total reward below a nonfatal candidate.
- Runtime-generated fatal candidates are still written to
  `candidate_reward_traces.jsonl` when they are not selected.
- Aggregate fatal/clamp counters distinguish tracked fatal candidates from
  selected fatal candidates.

## Performance And Metrics

This is test-only coverage. It does not change runtime code, data structures, or
production observability. The affected measurement is changed-scope test
coverage for the modified test files.

## Implementation Steps

- [x] Read #703, #701, the #702 plan, runner code, and existing GRPO tests.
- [x] Add a scored-trace regression test for fatal penalty without clamping.
- [x] Add a runtime-generated regression test for an unselected fatal timeout
      candidate in candidate reward traces.
- [x] Run focused tests, changed-scope coverage, `git diff --check`, and the
      relevant pre-commit/performance gate.

## Verification

Completed commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_agentic_grpo_reward_components.py services/mlx-worker-python/tests/test_rl_alignment_runtime_tool_trajectories.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py -k 'alignment_rl or grpo or rlhf or reward_model or rollout or structured_result'

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage run --data-file=/tmp/fatal_grpo_tests.coverage -m pytest -q services/mlx-worker-python/tests/test_agentic_grpo_reward_components.py services/mlx-worker-python/tests/test_rl_alignment_runtime_tool_trajectories.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py -k 'alignment_rl or grpo or rlhf or reward_model or rollout or structured_result'
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage json --data-file=/tmp/fatal_grpo_tests.coverage -o /tmp/fatal_grpo_tests_coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json /tmp/fatal_grpo_tests_coverage.json services/mlx-worker-python/tests/test_agentic_grpo_reward_components.py services/mlx-worker-python/tests/test_rl_alignment_runtime_tool_trajectories.py

git diff --check

python3 scripts/pre_commit_gate.py
```

Results:

- Focused fatal-aware GRPO tests: `12 passed`.
- Wider LoRA alignment subset: `29 passed, 106 deselected`.
- Combined touched Python subset: `40 passed, 107 deselected`.
- Changed-scope coverage: aggregate `100%` (`94` measurable changed lines,
  `0` missed lines).
- `git diff --check`: pass.
- Full pre-commit gate: `make swift-test` passed, `make py-test` passed with
  `2886 passed, 14 skipped`, and `make integration-test` passed with
  `114 passed, 1 skipped`.
- Performance report: `Status: ok`, `Selected probes: 0`,
  `Direct/gated probes: 0`, `Regressions: 0`; report written to
  `.runtime/pre-commit-performance/20260520-125013-20523388/report/report.md`.
