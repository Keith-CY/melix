# M17.1 Speech-To-Text Backend Adapters And Model Matrix

## Goal

Add real speech-to-text backend families to Melix with typed capability metadata, routing rules, and a stable compatibility matrix.

## Scope

- add `Whisper`-class and `Parakeet`-class backend adapters
- expose backend capabilities and model metadata
- add routing and compatibility checks for supported transcription models

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/model_registry/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `tests/integration/`

## Implementation Notes

- Backend-specific assumptions about chunking, timestamps, and language detection should remain adapter-local.
- Capability metadata must remain stable enough for both operator surfaces and API consumers.

## Verification

- `make py-test`
- `make swift-test`
- `make integration-test`

## Acceptance

- Real speech-to-text backend families are discoverable, routable, and test-covered.
- Model metadata distinguishes backend family and supported transcription capabilities.
