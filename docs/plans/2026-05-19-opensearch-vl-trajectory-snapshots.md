# OpenSearch-VL Trajectory Snapshot Metrics

## Goal

Complete the executable dataset-materialization slice for issues #669 and #670
under the OpenSearch-VL alignment parent #664.

## Scope

- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `services/mlx-worker-python/tests/test_training_dataset_builder.py`
- `services/mlx-worker-python/tests/test_lora_model_ops.py` only if LoRA
  preparation assertions need to prove job-local snapshot consumption.

## Plan

1. Extend `agentic_tool_trace` quality metrics with trace turn count min, max,
   and average, media reference count, reward coverage count, and fatal-stage
   field coverage count.
2. Add a deterministic normalized-snapshot trace digest for
   `agentic_tool_trace` datasets.
3. Persist snapshot manifest provenance required by the contract: source
   package path, selected split, quality metrics, trace digest, toolset version,
   reward policy id, and leakage policy id when available.
4. Add focused tests for the new metrics, snapshot manifest fields, JSONL row
   preservation, and non-agentic backward-compatible snapshot behavior.

## Metrics

- `agentic_trace_count`
- `trace_turn_count_min`
- `trace_turn_count_max`
- `trace_turn_count_avg`
- `tool_call_count`
- `tool_observation_count`
- `media_ref_count`
- `reward_coverage_count`
- `fatal_stage_coverage_count`
- `fatal_trace_count`
- `leakage_count`
- `trajectory_trace_digest`

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_training_dataset_builder.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" COVERAGE_FILE=/tmp/opensearch-vl-trajectory-snapshots.coverage uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" COVERAGE_FILE=/tmp/opensearch-vl-trajectory-snapshots.coverage uv run --project services/mlx-worker-python coverage json -o /tmp/opensearch-vl-trajectory-snapshots-coverage.json
uv run --project services/mlx-worker-python python scripts/python_changed_line_coverage.py --coverage-json /tmp/opensearch-vl-trajectory-snapshots-coverage.json --diff-from origin/main services/mlx-worker-python/worker/model_ops/training_dataset.py services/mlx-worker-python/tests/test_training_dataset_builder.py
git diff --check
```

## Known Gaps

- This slice does not add LoRA adapter, RL, benchmark, or evaluation artifact
  provenance fields; those remain assigned to #672 and #673.
- The trace digest proves snapshot content identity, not model quality.
- Explicit leakage terms remain deterministic string checks and do not replace
  semantic leakage review.
