# M12 Model Registry, Family Coverage, And Model Tools

## Goal

Complete the model-discovery and model-operations surface so Melix can scan multiple roots, serve a broader family matrix, and expose inspection, health, and conversion tools through one operator-visible registry model.

## Scope

- complete ordered multi-root model discovery
- broaden text, MoE, embedding, and image-family coverage
- add model inspection and health-check workflows
- add artifact conversion and quantized packaging workflows
- support independent embedding-model preload and selection

## Coverage

- default plus user-added model roots with ordered scanning and reload
- structured provider, organization, model, and variant identity
- expanded text-family coverage for `Mistral Small 4 (119B)`, `model_type: mistral4`, MLA attention, `128-expert MoE`, `YaRN interleaved RoPE`, `Nemotron-H`, and MoE gate-dequant paths
- expanded image-family dispatch for `Klein 4B/9B`, `Kontext`, `Fill`, `QwenImage`, and `FIBO`, with correct class-based routing rather than pattern-only dispatch
- model inspection metadata and health-check reporting
- HuggingFace-to-quantized-artifact workflow
- independent embedding-model preload and selection

## Execution Slices

- `M12.1` Multi-root registry management and rescan
- `M12.2` Text and MoE family adapters
- `M12.3` Image family dispatch and picker completion
- `M12.4` Model inspect, health, and conversion tools

## Files

- update `services/mlx-worker-python/worker/model_registry/`
- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/model_ops/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/WorkerClient/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `tests/integration/`

## Implementation Notes

- Family-specific behavior should remain adapter-driven instead of leaking into generic routing code.
- Inspection and health-check payloads should be typed and stable enough for both desktop rendering and CLI or API export.
- Conversion and packaging flows should reuse existing model-ops job infrastructure rather than bypassing it with direct worker actions.
- Root ordering and identity derivation must remain deterministic even when roots contain partial or invalid artifacts.

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`
- registry-and-tools smoke command for the touched scope

## Acceptance

- Multi-root discovery, family routing, inspection, and health tools are operator-visible and test-covered.
- Expanded family coverage can be loaded and exercised through live-path integration checks.
- Conversion and quantized packaging workflows are tied back to stable model metadata.
