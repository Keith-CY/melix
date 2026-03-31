# M6.1 OQ Quantization Pipeline

## Goal

Define the first real `oQ` quantization pipeline so quantize jobs produce serving-compatible artifact bundles with versioned metadata instead of placeholder manifest files.

## Scope

- define the first typed quantization profile contract and map legacy `weight_quant` and `kv_quant` inputs into it
- replace the placeholder quantize path with a staged worker pipeline that emits a bundle directory and `manifest.json`
- preserve the existing desktop and control-plane quantize workflow while exposing richer typed result metadata
- keep produced artifacts compatible with Melix serving flows and later upload or benchmark milestones

## Files

- update `packages/protocol/schema/worker/v1/maintenance.proto`
- update `packages/protocol/schema/controlplane/v1/control_plane.proto`
- regenerate protocol artifacts under `packages/protocol/swift`, `packages/protocol/python`, and `packages/protocol/descriptors`
- update `services/mlx-worker-python/worker/engine/maintenance_core.py`
- update `services/mlx-worker-python/worker/model_ops/`
- update `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- update `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- update `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`
- update quantization tests and metrics scripts

## Implementation Notes

- normalize legacy quantize requests into a typed `QuantizationProfile` with `algorithm=oq`, `schema_version=melix.quant_profile.v1`, and stable `quant_profile_id`
- emit staged progress for `resolve_source`, `normalize_profile`, `quantize_weights`, `write_bundle`, and `write_manifest`
- write quantized output as a bundle directory ending in `quantize.artifact` with `config.json`, `tokenizer.json`, `weights.safetensors`, and `manifest.json`
- keep `output_path` and `manifest_json` populated for compatibility, while also returning typed profile and artifact summaries through worker and control-plane results
- surface typed quantization summary in the desktop `Last Operation` panel without adding a new workflow

## Verification

- `make proto`
- `make swift-test`
- `make py-test`
- `make integration-test`
- touched-scope coverage command for the changed worker and Swift packages
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/phase5_model_ops_metrics.py`

## Acceptance

- quantize jobs produce bundle-directory artifacts and versioned machine-readable metadata
- worker events and control-plane results expose typed quantization profile and artifact summaries
- operator workflows can still launch and inspect quantize jobs through the existing desktop path
- metrics report captures quantize duration, artifact bytes, and manifest bytes for the new bundle output
