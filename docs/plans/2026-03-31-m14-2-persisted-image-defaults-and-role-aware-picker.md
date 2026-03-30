# M14.2 Persisted Image Defaults And Role-Aware Picker

## Goal

Persist image defaults across restart and expose role-aware model selection for generation and editing.

## Scope

- persist creative defaults such as steps, size, guidance, strength, and negative prompt
- add role-aware model picker behavior
- keep effective defaults inspectable after merge

## Files

- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `apps/macos-menubar/Sources/AppMain/Image/`
- update `apps/macos-menubar/Tests/MenuBarTests/`

## Implementation Notes

- Persisted defaults should not override explicit per-request inputs silently.
- Picker role visibility should be driven by capability metadata.
- Family-specific picker constraints should remain operator-visible.

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- Persisted image defaults survive restart and remain inspectable.
- Role-aware picking for generation and editing is test-covered.
