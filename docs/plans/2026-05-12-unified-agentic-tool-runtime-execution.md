# Unified Agentic Tool Runtime Execution Slice

## Goal

Implement the first executable issue #674 slice that reuses one deterministic
local tool runtime across SFT replay, benchmark, evaluation sample generation,
and RL alignment rollout.

## Non-Goals

- Network-backed search or browser access.
- Importing the upstream OpenSearch-VL training stack.
- Unsafe arbitrary Python execution.

## Context

- Governing spec: `docs/unified-agentic-tool-runtime-contract.md`
- Existing contracts:
  - `services/mlx-worker-python/worker/runtime/tool_registry.py`
  - `services/mlx-worker-python/worker/runtime/tool_observation.py`
- Execution targets:
  - `services/mlx-worker-python/worker/model_ops/training_dataset.py`
  - `services/mlx-worker-python/worker/engine/evaluation_core.py`
  - `services/mlx-worker-python/worker/engine/maintenance_core.py`
  - `services/mlx-worker-python/worker/model_ops/rl_alignment_training.py`

## Work Plan

1. Add a deterministic worker runtime for built-in agentic tools.
2. Replay `agentic_tool_trace` training rows with tool calls through the same
   runtime when precomputed turns are not already present.
3. Preserve tool-call and observation evidence on `EvaluationSample` JSONL
   payloads without changing existing CSV columns.
4. Execute case-level tool calls in benchmark request rows.
5. Execute sample-level tool calls in evaluation sample generation.
6. Execute the same sample-level tool calls in RL policy trace construction.
7. Add focused tests for adapters, SFT replay, benchmark persistence,
   evaluation persistence, and RL trace reuse.

## Verification

```bash
uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_agentic_tools.py services/mlx-worker-python/tests/test_evaluation_schemas.py services/mlx-worker-python/tests/test_evaluation_core.py -k 'agentic_tool or preserves_sample_payload or run_local_suite_executes_packaged_dataset'
uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_suites.py services/mlx-worker-python/tests/test_benchmark_schemas.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_benchmark_evaluation_report.py -k 'agentic_tool or canonical_fields or aggregates_agentic_tool_metrics'
uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py -k 'tool'
uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py -k 'agentic_tool_trace or agentic_tool_calls'
git diff --check
```

## Acceptance Criteria

- All six built-in tools execute through one runtime and emit
  `melix.agentic_tool_observation.v1` records.
- SFT `agentic_tool_trace` rows can replay local tool calls into the same
  assistant/tool turns, registry receipts, observations, and metrics.
- Evaluation samples can persist registry receipts, tool calls, observations,
  and aggregate tool metrics in JSONL artifacts.
- Benchmark request rows can persist the same registry receipts, tool calls,
  observations, and aggregate tool metrics in JSONL artifacts.
- RL alignment policy traces reuse the same runtime and observation shape.
- Documentation and PR evidence state network provider gaps explicitly.
