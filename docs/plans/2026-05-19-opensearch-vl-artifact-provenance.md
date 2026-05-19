# OpenSearch-VL Artifact Provenance

## Goal

Complete the artifact-provenance slice for OpenSearch-VL alignment issues
#671, #672, and #673.

## Scope

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`
- `services/mlx-worker-python/worker/model_ops/rl_alignment_training.py`
- `services/mlx-worker-python/worker/model_ops/training_config.py`
- `services/mlx-worker-python/worker/productization/benchmark_export.py`
- `services/mlx-worker-python/worker/productization/benchmark_schemas.py`
- `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- `services/mlx-worker-python/worker/productization/evaluation_store.py`
- `services/mlx-worker-python/worker/productization/run_evidence.py`
- Focused Python tests for the changed artifact writers and export schemas.

## Field Contract

Agentic trajectory provenance is a flat optional field set. Writers must omit
the fields for non-`agentic_tool_trace` datasets and preserve backward
compatibility for existing benchmark and evaluation exports.

- `trajectory_dataset_id`
- `trajectory_dataset_version`
- `trajectory_schema_version`
- `trajectory_snapshot_manifest_path`
- `trajectory_split`
- `trajectory_trace_digest`
- `trajectory_toolset_version`
- `trajectory_registry_schema_version`
- `trajectory_reward_policy_id`
- `trajectory_leakage_policy_id`
- `trajectory_package_path`
- `trajectory_quality_metrics`

The normalized training dataset snapshot manifest remains the source of truth.
Adapter, RL, benchmark, evaluation, and run-evidence writers should derive the
same field set from that manifest or from an already-normalized provenance map.

## Plan

1. Add a reusable provenance extractor for normalized training dataset snapshot
   manifests.
2. Add trajectory provenance to LoRA adapter manifests and RL alignment trace
   artifacts when the training dataset is `agentic_tool_trace`.
3. Add optional trajectory provenance to benchmark and evaluation schema
   records, JSON exports, CSV exports, and run-evidence domain results.
4. Keep non-agentic artifact semantics backward-compatible and make export
   changes append-only when optional provenance columns are introduced.
5. Add focused tests that prove provenance survives adapter packaging, RL trace
   writing, benchmark/evaluation stores, CSV exports, and run-evidence payloads.

## Metrics

- `trajectory_provenance_field_count`
- `trajectory_reward_policy_present`
- adapter manifest byte size
- RL policy update trace row count
- evaluation sample provenance coverage count
- benchmark row provenance coverage count
- run-evidence trajectory artifact reference count

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_benchmark_schemas.py services/mlx-worker-python/tests/test_benchmark_store.py services/mlx-worker-python/tests/test_evaluation_schemas.py services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_run_evidence.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py services/mlx-worker-python/tests/test_benchmark_schemas.py services/mlx-worker-python/tests/test_benchmark_store.py services/mlx-worker-python/tests/test_benchmark_export.py services/mlx-worker-python/tests/test_evaluation_schemas.py services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_run_evidence.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" COVERAGE_FILE=/tmp/opensearch-vl-artifact-provenance.coverage uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py services/mlx-worker-python/tests/test_benchmark_schemas.py services/mlx-worker-python/tests/test_benchmark_store.py services/mlx-worker-python/tests/test_benchmark_export.py services/mlx-worker-python/tests/test_evaluation_schemas.py services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_run_evidence.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" COVERAGE_FILE=/tmp/opensearch-vl-artifact-provenance.coverage uv run --project services/mlx-worker-python coverage json -o /tmp/opensearch-vl-artifact-provenance-coverage.json
uv run --project services/mlx-worker-python python scripts/python_changed_line_coverage.py --coverage-json /tmp/opensearch-vl-artifact-provenance-coverage.json --diff-from origin/main services/mlx-worker-python/worker/trajectory_provenance.py services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py services/mlx-worker-python/worker/model_ops/rl_alignment_training.py services/mlx-worker-python/worker/model_ops/training_config.py services/mlx-worker-python/worker/productization/benchmark_export.py services/mlx-worker-python/worker/productization/benchmark_schemas.py services/mlx-worker-python/worker/productization/evaluation_schemas.py services/mlx-worker-python/worker/productization/evaluation_store.py services/mlx-worker-python/worker/productization/run_evidence.py
git diff --check
```

## Known Gaps

- This plan does not add a new UI surface for browsing trajectory provenance.
- The trace digest identifies the normalized dataset content; it is not a
  reward-quality score.
- Existing benchmark and evaluation callers must pass provenance explicitly
  until a higher-level runner wires dataset-package discovery into every run.
