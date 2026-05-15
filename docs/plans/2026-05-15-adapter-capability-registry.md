# Adapter Capability Registry For Advanced Training Modes

Issue: [#935](https://github.com/Keith-CY/melix/issues/935)

## Goal

Productize a typed adapter capability registry for Melix training and adapter
activation so future LoRA-like, ReLoRA-compatible, and extension-provided
adapter families enter through stable capability contracts instead of scattered
adapter-name checks.

This plan keeps the existing LoRA and QLoRA operator path stable while adding
explicit admission and receipt fields for adapter-family capabilities, backend
support, quantized-base compatibility, merge/export eligibility, and typed
unsupported reasons.

## Current Problem

The Python worker currently resolves training behavior from `training_mode`,
family profiles, and several local conditionals:

- `training_mode=qlora` checks whether the base model is quantized.
- family ids such as `qwen3moe` can be enabled or blocked through family hook
  metadata.
- target-module safety for quantized LoRA is enforced by direct target-name
  predicates.
- adapter manifests record `training_mode`, `adapter_algorithm`, and
  `quantization_mode`, but do not expose the effective adapter capabilities or
  a stable reason when a capability is unavailable.

Those checks work for the current built-in LoRA/QLoRA path, but they do not give
extension providers a typed place to declare LoRA-like behavior, merge support,
ReLoRA compatibility, quantized-base support, or backend-specific refusal.

## Contract

Add a worker-owned registry with these core fields:

- `adapter_family`: stable family id used by manifests and receipts.
- `adapter_algorithm`: backend algorithm id such as `lora`, `dora`, or a
  future extension id.
- `capabilities`: booleans for `lora_like`, `mergeable`,
  `relora_compatible`, and `quantized_base_supported`.
- `backend_supported`: whether the selected worker backend can honor the
  adapter contract.
- `unsupported_reason`: empty when admitted, otherwise a typed reason such as
  `missing_adapter_provider`, `unsupported_backend`,
  `unsupported_quantized_base`, `missing_quantization_provider`, or
  `non_mergeable_adapter`.
- `loader_kwargs`: safe provider-supplied kwargs that are forwarded to the
  adapter loader namespace when the backend supports the contract.

The registry must provide built-in entries for the current LoRA-compatible
training modes and a local test-only registration path for extension fixtures.

## Implementation Slices

### Slice 1 - Capability Model

- Add a Python worker module that defines `AdapterCapabilities`,
  `AdapterCapabilityRecord`, `AdapterCapabilityRegistry`, and typed
  unsupported reason constants.
- Register built-in adapter contracts for `lora`, `qlora`, and `dora`.
- Keep current default behavior unchanged for built-in LoRA workflows.
- Make unknown adapter families fail during config normalization with
  `missing_adapter_provider` before any model load or backend execution.

### Slice 2 - Training Admission And Loader Integration

- Thread the selected capability record into `LoRATrainingConfig`.
- Replace adapter-name and training-mode admission checks with registry
  predicates where the decision is about adapter capability rather than dataset
  shape or target-module topology.
- Preserve existing target-module and family profile validation for model
  topology because those are still family-specific model-shape concerns.
- Forward registry `loader_kwargs` into the MLX-LM LoRA namespace so extension
  adapters can prove loader integration without real external packages.

### Slice 3 - Receipts, Merge/Export Gates, And Evidence

- Emit adapter capability receipt fields in `train_lora.adapter.json`:
  `adapter_family`, `adapter_capabilities`, `backend_supported`, and
  `unsupported_reason`.
- Carry the same capability receipt into activation manifests.
- Gate fused activation on `mergeable`; non-mergeable adapters must fail with
  `non_mergeable_adapter` while `adapter_backed_runtime` can still be admitted
  when the adapter is otherwise backend-supported.
- Add tests for a fake extension adapter that proves registry-driven
  validation, loader kwargs, ReLoRA compatibility metadata, and merge/export
  gating.
- Add quantized-base fixtures proving `unsupported_quantized_base` and
  `missing_quantization_provider` fail before backend model load and that
  receipts distinguish adapter unsupported from quantization unsupported.

## Performance And Metrics

The changed path is Python worker config normalization and manifest assembly.
The expected overhead is constant-time dictionary lookup plus small JSON receipt
fields per adapter-backed operation.

Local metrics:

- changed-scope coverage for the new registry module and focused LoRA tests must
  be at least 95 percent.
- focused tests must include existing LoRA/QLoRA happy paths and new negative
  admission paths.
- no new PR-scoped performance probe is required for this slice because no hot
  tokenization, dataset scan, model-load, or streaming loop is changed. The
  hosted PR-scoped performance workflow remains the final regression gate.

## Verification

Focused local commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_adapter_capability_registry.py \
  services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_supports_qlora_with_hf_valid_split_and_persists_desired_alias \
  services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_supports_dora_mode_contract_and_manifest \
  services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_rejects_qlora_for_non_quantized_base_model \
  services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_resolves_qwen3moe_expert_preset_and_adapter_backed_activation \
  services/mlx-worker-python/tests/test_lora_model_ops_unit.py::test_normalize_training_config_rejects_unknown_modes_and_families

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_adapter_capability_registry.py \
  services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_supports_qlora_with_hf_valid_split_and_persists_desired_alias \
  services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_supports_dora_mode_contract_and_manifest \
  services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_rejects_qlora_for_non_quantized_base_model \
  services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_resolves_qwen3moe_expert_preset_and_adapter_backed_activation \
  services/mlx-worker-python/tests/test_lora_model_ops_unit.py::test_normalize_training_config_rejects_unknown_modes_and_families
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/model_ops/adapter_capabilities.py \
  services/mlx-worker-python/worker/model_ops/training_config.py \
  services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py \
  services/mlx-worker-python/worker/model_ops/adapter_activation_pipeline.py \
  services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py \
  services/mlx-worker-python/tests/test_adapter_capability_registry.py
```

Repository gates before PR:

```bash
make py-test
```

Full pre-commit gates may run through the repository hook on high-memory macOS.
The PR must also pass hosted CI and the PR-scoped performance report before the
issue is considered complete.

## Success Criteria

- Issue #935 has a PR linked from this plan.
- Built-in LoRA, QLoRA, and DoRA paths preserve existing behavior.
- Unknown adapter families fail before backend load with
  `missing_adapter_provider`.
- Quantized-base mismatch and unknown quantization provider fail before backend
  load with typed reasons.
- Training and activation manifests record effective adapter capability receipt
  fields.
- A fake extension adapter fixture proves registry-driven validation, loader
  kwargs, ReLoRA compatibility fields, and merge/export gating.
- Local focused coverage for the changed scope is at least 95 percent.
- Hosted CI and PR performance report finish without unresolved failures or
  regressions.
