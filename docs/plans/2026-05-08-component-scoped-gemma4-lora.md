# Component-Scoped Gemma 4 LoRA Support

## Purpose

Melix should not reject a downloaded Gemma 4 multimodal model when the downloaded
model exposes a trainable Gemma text backbone. The long-term contract is
component-scoped adapter training: model discovery records which local component
is trainable, LoRA validation targets that component, and adapter lifecycle
artifacts preserve the component scope for activation and later catalog
registration.

## Scope

This slice productizes the Gemma 4 `text_backbone` LoRA surface for local VLM
model specs whose `config.json` exposes `text_config.model_type == "gemma4_text"`.
It applies to both text-backed Gemma 4 snapshots and full multimodal Gemma 4
snapshots. The source model remains a VLM model for runtime routing, while LoRA
training uses the text-backbone family contract.

Out of scope:

- vision encoder LoRA
- multimodal projector LoRA
- audio component LoRA
- fused multimodal activation for component-scoped adapters

Those surfaces require separate adapter contracts and runtime loading behavior
before they can be marked training-ready.

## Design

Model discovery emits explicit component metadata for Gemma 4 VLM specs:

- `melix.model.components`
- `melix.component.text_backbone.model_type`
- `melix.component.text_backbone.family_id`
- `melix.component.text_backbone.lora_supported`
- `melix.component.text_backbone.training_ready`
- `melix.component.vision_encoder.lora_supported`
- `melix.component.multimodal_projector.lora_supported`

The LoRA-facing compatibility keys remain under the existing `melix.lora.*`
namespace so existing family resolution can reuse the stable Gemma mapper:

- `melix.lora.adapter_scope = text_backbone`
- `melix.lora.training_surface = text_backbone`
- `melix.lora.base_model_path = <local model directory>`
- `melix.lora.component_model_type = gemma4_text`
- `melix.lora.family_id = gemma`
- `melix.lora.training_ready = true`

`normalize_training_config` stops using `model_kind == "text"` as the only
admission rule. Text models stay supported. Non-text models are admitted only
when the registry has marked a known component training surface as
training-ready. Gemma 4 VLMs without component metadata and all embedding/image
models remain rejected with `unsupported_model_family`.

Training manifests record the adapter scope, training surface, source model
kind, component model type, component family, and component path. Activation
validates those fields against the requested source model. Adapter-backed
runtime activation is allowed for the `text_backbone` scope; fused activation is
rejected for non-text source models until a fused multimodal component contract
exists.

Derived-model registration and registry snapshots propagate the adapter scope so
operators and runtime consumers can tell that a derived VLM entry is backed by a
text-backbone adapter rather than an opaque whole-model adapter.

## Performance Probes And Metrics

This change does not add a new optimizer loop. The relevant probes are:

- training request dispatch path: verify the backend receives the component
  model path selected from `melix.lora.base_model_path`
- training manifest write path: verify adapter scope and component metadata are
  emitted deterministically
- activation validation path: verify mismatched scopes fail before runtime load
- derived registration path: verify adapter scope survives catalog restoration

Success metrics:

- targeted Python tests covering registry, training config, training manifest,
  activation validation, and derived registration pass
- changed-line coverage for touched Python files is at least 95 percent, or the
  PR reports why a touched documentation-only path is not measurable
- `git diff --check` passes

## Verification Plan

Targeted checks:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --locked --project services/mlx-worker-python --extra mlx pytest \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_promotes_gemma4_text_manifest_to_vlm_text_backed \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_keeps_multimodal_gemma4_manifest_in_multimodal_mode \
  services/mlx-worker-python/tests/test_lora_model_ops_unit.py::test_normalize_training_config_rejects_non_text_models \
  services/mlx-worker-python/tests/test_lora_model_ops_unit.py::test_normalize_training_config_accepts_gemma4_vlm_text_backbone_scope \
  services/mlx-worker-python/tests/test_lora_model_ops_unit.py::test_lora_training_pipeline_uses_component_scope_metadata_for_gemma4_vlm \
  services/mlx-worker-python/tests/test_lora_model_ops_unit.py::test_adapter_activation_pipeline_validates_component_scope_for_vlm_adapters \
  services/mlx-worker-python/tests/test_lora_model_ops.py::test_activate_adapter_supports_adapter_backed_runtime_and_uses_training_alias \
  -q
```

Coverage:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" COVERAGE_FILE="$(pwd)/.coverage.component_lora" uv run --locked --project services/mlx-worker-python --extra mlx coverage run -m pytest <targeted tests> -q
uv run --locked --project services/mlx-worker-python --extra mlx coverage json -o coverage.component_lora.json
python3 scripts/python_changed_line_coverage.py --coverage-json coverage.component_lora.json <changed python files>
```
