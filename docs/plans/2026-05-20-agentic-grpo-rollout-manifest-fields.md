# Agentic GRPO Rollout Manifest Fields

## Goal

Implement issue #697 by adding a stable rollout manifest projection for
candidate count, reward policy, reference model, and trajectory digest. This
continues Milestone 1 for the OpenSearch-VL online GRPO/RL rollout direction
after the reward-component contract landed in issue #696.

## Scope

- Governed issue: #697.
- Parent direction: #694, OpenSearch-VL alignment: online GRPO/RL rollout for
  tool-use LoRA.
- Runtime boundary: Python worker alignment artifact construction.
- Artifact boundary: adapter manifest, alignment run manifest, adapter config,
  and `policy_updates.jsonl`.

## Architecture

Melix already persists scalar alignment settings such as
`grpo_candidate_count`, `reference_model_path`, `reward_model_manifest_path`,
`candidate_generation_mode`, and `candidate_scoring_mode`. This slice adds a
single rollout manifest projection so later online rollout, fatal-aware GRPO,
benchmark, and evaluation slices can consume the same provenance keys without
reconstructing them from mode-specific fields.

The v1 projection is:

- `rollout_manifest_schema_version`: names the stable projection schema.
- `rollout_candidate_count`: configured GRPO candidate count, or `1` for RLHF.
- `rollout_reward_policy_id`: trajectory provenance policy id when available;
  otherwise a deterministic built-in policy id based on scoring mode.
- `rollout_reference_model_path`: explicit reference path when supplied,
  otherwise the resolved source model path for the run.
- `rollout_trajectory_digest`: trajectory provenance digest when available,
  otherwise a deterministic digest of the policy-update rows.

The worker computes this projection once at the alignment runner boundary and
passes it through `TrainingMetrics` so the pipeline manifest reuses the same
values. This keeps adapter config, policy updates, adapter manifest, and
alignment run manifest consistent.

## Performance And Metrics

The only new computation is a SHA-256 digest over policy-update rows when no
source trajectory digest exists. The rows are already in memory and already
written to `policy_updates.jsonl`, so this adds no model execution, network
calls, broad filesystem scans, or extra runtime invocations.

Success metrics:

- Adapter manifest and alignment run manifest include all rollout manifest
  fields.
- Adapter config and policy-update trace rows include the same rollout manifest
  fields.
- Source trajectory provenance overrides the default reward policy id and
  digest when present.
- Reward-model scoring records the reward-model rollout policy id.
- Changed-line coverage for touched Python files is at least 95 percent.

## Implementation Steps

- [x] Update the trajectory contract with rollout manifest field semantics.
- [x] Add a Python helper for the shared rollout manifest projection.
- [x] Attach rollout fields to adapter config and policy-update rows in the
      alignment runner.
- [x] Propagate runner-computed rollout fields through training metrics into
      adapter and alignment manifests.
- [x] Add focused tests for default GRPO, reward-model GRPO, RLHF, and
      trajectory-provenance-backed rollout artifacts.

## Verification

Results:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_agentic_grpo_reward_components.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py::test_mlx_lm_runner_scores_generated_grpo_candidates_with_reward_model services/mlx-worker-python/tests/test_trajectory_provenance.py::test_alignment_rl_trace_runner_attaches_trajectory_provenance services/mlx-worker-python/tests/test_trajectory_provenance.py::test_alignment_manifest_payload_records_trajectory_provenance_metrics
# 9 passed

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_supports_rl_alignment_mode_contracts services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_records_runtime_generated_grpo_evidence
# 3 passed

git diff --check
# passed

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" COVERAGE_FILE=/tmp/agentic_rollout_manifest.coverage uv run --frozen --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_agentic_grpo_reward_components.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" COVERAGE_FILE=/tmp/agentic_rollout_manifest.coverage uv run --frozen --project services/mlx-worker-python coverage run --append -m pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py -k 'alignment_mode_contracts or runtime_generated_grpo_evidence or reward_model_scored_rlhf'
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" COVERAGE_FILE=/tmp/agentic_rollout_manifest.coverage uv run --frozen --project services/mlx-worker-python coverage run --append -m pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py -k 'grpo or rlhf or reward_model or rollout'
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" COVERAGE_FILE=/tmp/agentic_rollout_manifest.coverage uv run --frozen --project services/mlx-worker-python coverage run --append -m pytest -q services/mlx-worker-python/tests/test_trajectory_provenance.py -k 'alignment_rl_trace_runner or alignment_manifest_payload'
# 6 passed; 4 passed, 67 deselected; 12 passed, 123 deselected; 2 passed, 9 deselected

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" COVERAGE_FILE=/tmp/agentic_rollout_manifest.coverage uv run --frozen --project services/mlx-worker-python coverage json -o /tmp/agentic_rollout_manifest_coverage.json
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python python scripts/python_changed_line_coverage.py --coverage-json /tmp/agentic_rollout_manifest_coverage.json services/mlx-worker-python/worker/model_ops/alignment_rollout_manifest.py services/mlx-worker-python/worker/model_ops/rl_alignment_training.py services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py services/mlx-worker-python/tests/test_agentic_grpo_reward_components.py services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py services/mlx-worker-python/tests/test_trajectory_provenance.py
# TOTAL 98.37% (121/123)

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_CHANGED_SCOPE_BASE_ROOT="$PWD" MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON='["services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py"]' uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py::test_alignment_percentile_uses_interpolation_and_upper_bound services/mlx-worker-python/tests/test_lora_model_ops.py::test_reward_summary_reuses_candidate_group_minmax services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_supports_rl_alignment_mode_contracts services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_supports_qlora_with_hf_valid_split_and_persists_desired_alias services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_lora_reward_summary_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_lora_reward_summary_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_lora_reward_summary_probe_script_main_covers_checked_in_file
# 9 passed

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_CHANGED_SCOPE_BASE_ROOT="$PWD" MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON='["services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py"]' uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py::test_run_subprocess_extracts_terminal_structured_result_without_splitlines services/mlx-worker-python/tests/test_lora_model_ops_unit.py::test_run_subprocess_rejects_missing_structured_result services/mlx-worker-python/tests/test_lora_model_ops_unit.py::test_extract_structured_result_payload_accepts_carriage_return_line_end services/mlx-worker-python/tests/test_lora_model_ops_unit.py::test_extract_structured_result_payload_skips_embedded_prefix_and_finds_prior_line services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_mlx_lm_runner_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_mlx_lm_result_tail_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_mlx_lm_result_tail_probe_script_main_covers_checked_in_file
# 8 passed
```

The repository pre-commit gate remains pending for the final commit.
