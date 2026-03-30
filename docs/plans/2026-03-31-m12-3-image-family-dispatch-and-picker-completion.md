# M12.3 Image Family Dispatch And Picker Completion

## Goal

Complete image-family dispatch and picker visibility for the supported creative model families.

## Scope

- add class-based dispatch for supported image families
- expose picker metadata for generation and editing roles
- keep family support operator-visible in the product shell

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/model_registry/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/Image/`

## Implementation Notes

- Dispatch should use stable family classes rather than regex-only naming logic.
- Picker state should remain grounded in capability metadata.
- Family-specific constraints should stay discoverable in operator-visible metadata.

## Verification

- `make py-test`
- `make swift-test`
- `make integration-test`

## Acceptance

- Supported image families dispatch through the correct runtime class.
- Picker coverage for those families is complete and test-covered.
