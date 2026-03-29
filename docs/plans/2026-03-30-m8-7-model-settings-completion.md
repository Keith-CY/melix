# M8.7 Model Settings Completion

## Goal

Complete the per-model settings surface so operators can manage aliasing, type override, fallback behavior, resource input, and merged sampling controls coherently.

## Scope

- complete the model-settings surface
- preserve non-destructive settings merging
- keep effective settings visible after policy resolution

## Files

- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- update `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- update `apps/macos-menubar/Tests/MenuBarTests/`

## Implementation Notes

- settings resolution should remain deterministic across defaults, registry metadata, and operator overrides
- fallback behavior should be explicit rather than inferred
- preserve room for generation-config import in the next slice

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- the completed model-settings surface is operator-visible and test-covered
- effective settings can be inspected after merges and overrides
