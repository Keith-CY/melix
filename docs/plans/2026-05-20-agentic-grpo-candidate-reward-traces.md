# Agentic GRPO Candidate Reward Traces

## Goal

Implement issue #700 by persisting candidate-level reward traces and selected
candidate evidence for online GRPO rollout. This completes Milestone 2 of the
OpenSearch-VL online GRPO/RL rollout direction by making every generated
candidate auditable outside the selected policy-update row.

## Scope

- Governed issue: #700.
- Parent direction: #694, OpenSearch-VL alignment: online GRPO/RL rollout for
  tool-use LoRA.
- Milestone issue: #698, online candidate generation and scoring.
- Runtime boundary: Python worker alignment runner.
- Artifact boundary: adapter output directory and LoRA alignment run manifest.

## Architecture

The #699 runtime-generation slice records generated candidates inside each
`policy_updates.jsonl` row and projects the selected candidate tool trajectory
onto the policy-update row. That proves the selected update is tool-aware, but
it still makes group-wide candidate evidence hard to consume without parsing a
nested policy row.

This slice introduces a first-class candidate reward trace artifact:

- `candidate_reward_traces.jsonl`
- schema version `melix.alignment_candidate_reward_trace.v1`
- one row per candidate in each GRPO group

Each row records sample and candidate identity, candidate text, scalar score,
ordered reward components, fatal stage, selection state, group reward context,
scoring and generation backends, tool-call summary, selected candidate evidence
for the winner, and a deterministic replay fingerprint. The policy-update row
keeps the selected update and points to the candidate artifact through stable
path/count fields. The adapter config and alignment run manifest also expose
the path and count so downstream compare, release-gate, and evaluation slices
can load the candidate evidence directly.

The trace artifact is additive. Existing `policy_updates.jsonl` and embedded
`generated_candidates` fields remain available for legacy consumers.

## Performance And Metrics

The new work serializes candidate evidence that is already produced by the
runtime-generation path. It does not add policy model loads, reward model
loads, tool executions, network calls, or broad filesystem scans. Runtime cost
is proportional to candidate count and JSONL row size.

Measurement points:

- `candidate_reward_trace_count`
- `candidate_reward_trace_path`
- `candidate_reward_trace_schema_version`
- existing `generated_candidate_count`
- existing `agentic_tool.*` metrics inside candidate evidence

Success metrics:

- Every runtime-generated GRPO candidate has a row in
  `candidate_reward_traces.jsonl`.
- The selected candidate row carries `selected: true`, selected-candidate tool
  evidence, and the same reward components as the policy-update row.
- Alignment run metrics and adapter config expose the candidate trace path,
  count, and schema version.
- Existing text-only and reward-model scoring paths remain compatible.
- Changed-line coverage for touched Python files is at least 95 percent.

## Implementation Steps

- [x] Create the issue-specific plan before broad code changes.
- [x] Add candidate reward trace rows to the runtime GRPO policy update result.
- [x] Write the candidate trace artifact beside `policy_updates.jsonl`.
- [x] Surface candidate trace path/count/schema in adapter config and LoRA
      alignment run metrics.
- [x] Update governing contracts.
- [x] Add focused tests for artifact persistence and selected-candidate
      evidence.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_rl_alignment_runtime_tool_trajectories.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_records_runtime_generated_grpo_evidence

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py -k 'alignment_rl or grpo or rlhf or reward_model or rollout or structured_result'

git diff --check
```

Current changed-line coverage:

- `rl_alignment_training.py`: 97.56 percent, 40/41 measured changed lines.
- `mlx_lm_runner.py`: 100 percent, 3/3 measured changed lines.
- `lora_training_pipeline.py`: 100 percent, 3/3 measured changed lines.
- `test_rl_alignment_runtime_tool_trajectories.py`: 100 percent, 29/29 measured
  changed lines.
- `test_lora_model_ops_unit.py`: 100 percent, 6/6 measured changed lines.
- Aggregate: 98.78 percent, 81/82 measured changed lines.

PR-scoped performance probes selected by the changed files:

- `mlx-lm-structured-result-tail-parse`
- `lora-reward-summary-candidate-minmax`

Probe metric snapshots:

- `mlx_lm_result_tail_probe.py`: `elapsed_ms_mean=0.045475`,
  `peak_bytes_mean=1665.4`, `sample_count=5`.
- `lora_reward_summary_probe.py`: `elapsed_ms_mean=20.95531237500836`,
  `sorted_calls_mean=2`, `sample_count=5000`.

Pre-commit gate:

- `make swift-test`: pass.
- `make py-test`: pass, 2881 passed, 14 skipped.
- `make integration-test`: pass, 114 passed, 1 skipped.
- PR-scoped performance report:
  `.runtime/pre-commit-performance/20260520-095234-0a14599f/report/report.md`.
  The report marked `mlx-lm-structured-result-tail-parse` as a direct
  regression because `elapsed_ms_mean` moved from 0.071 ms to 0.076 ms
  (+0.005 ms, +7.55 percent). This change only adds `TrainingMetrics`
  dataclass fields and does not modify `_extract_structured_result_payload` or
  the tail-parse hot path. Five immediate local reruns of
  `scripts/mlx_lm_result_tail_probe.py` produced head samples between
  0.071050 ms and 0.082133 ms, so the reported delta is within probe noise for
  this microbenchmark. The LoRA reward summary probe remained ok.

Review follow-up:

- Applied the low-risk readability review items in
  `rl_alignment_training.py` by removing redundant casts and guards in the
  candidate trace row construction path.
- Re-ran the focused tests plus `git diff --check`: 31 passed, 107 deselected.
- Re-ran changed-line coverage: aggregate 98.78 percent, 81/82 measured changed
  lines.
