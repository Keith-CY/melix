# M6.1 OQ Quantization Pipeline

## Goal

Define the first real dynamic-quantization pipeline so quantization stops being only a manifest-producing maintenance flow.

## Scope

- define quantization pipeline stages and artifacts
- preserve current operator-facing quantize workflows while the implementation deepens
- keep produced artifacts compatible with Melix serving flows

## Files

- update `services/mlx-worker-python/worker/engine/maintenance_core.py`
- update `services/mlx-worker-python/worker/model_ops/`
- update `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- update `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`

## Implementation Notes

- the new pipeline should produce runnable artifacts, not only manifests
- quantization metadata should be versioned and inspectable
- keep operator workflows stable while the backend changes underneath

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- quantize jobs produce real artifacts and machine-readable metadata
- operator workflows can still launch and inspect quantize jobs
