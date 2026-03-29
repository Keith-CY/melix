# M6.10 HuggingFace Hub Upload For Quantized Artifacts

## Goal

Allow produced quantized artifacts to be published directly to HuggingFace Hub through the same operator tooling surface that launches quantization.

## Scope

- connect quantized-artifact metadata to upload workflows
- preserve operator visibility into produced artifacts and upload targets
- keep upload flows auditable and reproducible

## Files

- update `services/mlx-worker-python/worker/model_ops/`
- update `services/mlx-worker-python/worker/engine/maintenance_core.py`
- update `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- update `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`

## Implementation Notes

- upload workflows should consume artifact metadata from the quantization result rather than implicit path guesses
- publication targets should remain explicit and operator-visible
- keep upload and quantize manifests linkable for later diagnostics

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- quantized artifacts can be published through the productized upload path
- quantize-to-upload linkage is explicit and test-covered
