# M12.4 Model Inspect, Health, And Conversion Tools

## Goal

Expose model inspection, health checking, and conversion tooling as stable operator workflows tied to model metadata.

## Scope

- add inspect-model output and health-check reporting
- add conversion and quantized packaging entrypoints
- keep tools visible through model and tools surfaces

## Files

- update `services/mlx-worker-python/worker/model_ops/`
- update `services/control-plane-swift/Sources/WorkerClient/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `apps/macos-menubar/Sources/AppMain/`

## Implementation Notes

- Inspection payloads should remain typed and machine-readable.
- Health checks should report actionable failures instead of generic pass or fail output.
- Conversion should remain a model-ops job with explicit result metadata.

## Verification

- `make py-test`
- `make swift-test`
- `make integration-test`

## Acceptance

- Inspect, health, and conversion tools are operator-visible and test-covered.
- Tool results remain tied to stable model identity and manifests.
