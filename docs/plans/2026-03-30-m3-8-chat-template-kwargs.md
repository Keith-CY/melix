# M3.8 Chat Template Kwargs

## Goal

Add chat-template keyword-argument support at the model and request levels, with explicit forced overrides where product policy requires them.

## Scope

- add per-model template kwargs
- add per-request template kwargs
- add forced values that cannot be overridden by API callers

## Files

- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- update `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`

## Implementation Notes

- effective template kwargs should be inspectable after policy resolution
- forced values should win deterministically over request-level overrides
- keep the merge model compatible with future generation-config import work

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- chat-template kwargs can be configured per model and per request
- forced values are applied deterministically and are test-covered
