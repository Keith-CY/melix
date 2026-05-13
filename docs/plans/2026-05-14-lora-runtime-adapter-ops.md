# LoRA Runtime Adapter Operations

Issue: [#982](https://github.com/Keith-CY/melix/issues/982)

## Goal

Productize the LoRA runtime-operations layer so adapter-backed Melix models can be reasoned about as runtime assets, not only as training artifacts. This slice covers three product questions:

- Dynamic adapter switching: can multiple adapters share a loaded base model and switch without a full base reload?
- Quantized compatibility: how does LoRA behave with quantized base weights such as 4-bit and 8-bit MLX models?
- Concurrent use: how are adapter-backed requests isolated while still exposing safe base-model sharing?

## Current Baseline

Melix already supports LoRA and QLoRA training, adapter-backed activation, adapter-native evaluation compare, experiment history, and publish lineage. The remaining gap is operational metadata: the worker can load adapter-backed derived models, but artifacts and snapshots do not yet expose a stable runtime plan that operators, CI probes, and release reports can inspect.

## Design

### Runtime Reuse Contract

Each adapter-backed activation records:

- `adapter_runtime.base_reuse_key`: a deterministic hash of the base model identity, base path, revision, quantization profile, runtime mode, adapter scope, and trainable component path.
- `adapter_runtime.adapter_isolation_key`: a deterministic hash of the base reuse key plus adapter manifest path, adapter weights path, adapter hash, activation mode, and derived model id.
- `adapter_runtime.switch_mode`: `base_reuse_adapter_swap` for adapter-backed derived models and `full_model_load` for fused outputs.
- `adapter_runtime.sharing_policy`: `shared_base_isolated_adapter` for adapter-backed derived models and `isolated_fused_model` for fused outputs.
- `adapter_runtime.compatibility_status`: `compatible`, `incompatible`, or `unknown`.

The keys are evidence fields, not a promise that every backend has a hot adapter-swap primitive. They let Melix answer whether two adapter-backed targets are safe candidates for shared base residency and whether they must remain isolated at the adapter layer.

### Quantized Compatibility Contract

Training and activation artifacts record:

- quantized-base detection
- quantized base kind (`4bit`, `8bit`, `q4`, `q8`, `optiq`, or `unknown`)
- quantization profile id
- whether the requested training mode is QLoRA-compatible with the base
- whether quantized target-module guards accepted the selected LoRA targets

This keeps the current guard rails while making the operator-visible evidence explicit.

### Concurrency Contract

Concurrent adapter-backed targets that share the same base model must have the same `base_reuse_key` and distinct `adapter_isolation_key` values. Compare-only ephemeral adapter targets reuse the same contract so evaluation compare can load multiple adapters without colliding in the registry.

## Commit Slices

1. Planning contract
   - Add this plan.
   - Record issue, split, acceptance, metrics, and real LoRA validation command.

2. Runtime switching metadata
   - Add a Python worker helper for adapter runtime plans.
   - Write runtime switching fields into activation manifests.
   - Preserve those fields through model registration and registry snapshots.

3. Quantized compatibility metadata
   - Record quantized-base compatibility evidence in training manifests.
   - Carry the compatibility evidence into adapter-backed activation manifests.

4. Concurrent adapter isolation and compare sharing
   - Add deterministic non-colliding isolation keys for compare-time ephemeral adapter targets.
   - Add tests proving shared-base grouping and adapter isolation.

5. Real LoRA acceptance and PR evidence
   - Run the real LoRA workflow using `unsloth/gemma-4-E4B-it-MLX-8bit` and the dialogue extraction evaluation dataset.
   - Capture or report the exact environmental blocker.
   - Open the PR and monitor CI plus the Performance Report comment.

After every implementation commit, merge `origin/main` into the feature branch before continuing.

## Success Metrics

- Adapter-backed activation manifests expose stable runtime switching fields.
- Registry snapshots preserve runtime switching fields for derived adapter-backed models.
- Quantized training artifacts expose quantized-base detection and compatibility status.
- Compare-time adapter targets sharing one base produce equal base reuse keys and distinct isolation keys.
- Focused Python changed-scope coverage is at least 95 percent for touched worker paths.
- Real LoRA acceptance emits a machine-readable evidence bundle, or the PR records the exact local environment blocker.

## Verification

Focused deterministic verification:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_lora_model_ops_unit.py \
  services/mlx-worker-python/tests/test_lora_model_ops.py \
  services/mlx-worker-python/tests/test_evaluation_core.py
```

Changed-scope coverage:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python coverage run --data-file /tmp/lora_runtime_adapter_ops.coverage \
  --source=services/mlx-worker-python/worker,services/mlx-worker-python/tests \
  -m pytest -q \
  services/mlx-worker-python/tests/test_lora_model_ops_unit.py \
  services/mlx-worker-python/tests/test_lora_model_ops.py \
  services/mlx-worker-python/tests/test_evaluation_core.py

PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python coverage json \
  --data-file /tmp/lora_runtime_adapter_ops.coverage \
  -o /tmp/lora_runtime_adapter_ops.coverage.json

python3 scripts/python_changed_line_coverage.py \
  --coverage-json /tmp/lora_runtime_adapter_ops.coverage.json \
  services/mlx-worker-python/worker/model_ops/adapter_activation_pipeline.py \
  services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py \
  services/mlx-worker-python/worker/productization/evaluation_compare.py \
  services/mlx-worker-python/tests/test_lora_model_ops_unit.py \
  services/mlx-worker-python/tests/test_lora_model_ops.py \
  services/mlx-worker-python/tests/test_evaluation_core.py
```

Real LoRA acceptance target:

```bash
MELIX_REAL_LORA_MODEL_ID="unsloth/gemma-4-E4B-it-MLX-8bit" \
MELIX_REAL_LORA_DATASET_ID="dialogue-extraction" \
MELIX_REAL_LORA_ACCEPTANCE=1 \
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python --extra mlx \
  python scripts/phase8_lora_cli_smoke.py --json
```

The acceptance runner may need to be extended if the existing smoke script cannot target the dialogue extraction evaluation fixture directly. The PR must record the final evidence path or the exact blocker.

## Risks

- A backend may still reload the base model internally even when metadata says two adapters share a base. This plan records shareability first; backend hot-swap can be separately optimized behind the same contract.
- Quantized model identity can be inferred from names and metadata today. The implementation must prefer explicit quantization fields when present and treat name-based detection as evidence only.
- Concurrent compare targets are transient. Cleanup remains the runtime responsibility; this slice adds isolation evidence and collision prevention, not a new scheduler.

