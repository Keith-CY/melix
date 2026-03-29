# M3.3 Adaptive Thinking

## Goal

Add adaptive thinking controls so reasoning behavior can vary by request or model policy without fragmenting the core execution model.

## Scope

- define adaptive-thinking request and model-policy controls
- preserve compatibility with reasoning deltas and thinking blocks
- make adaptive behavior observable in metrics and operator state

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`

## Implementation Notes

- adaptive controls should compose with forced settings and per-request overrides
- keep policy resolution deterministic and easy to inspect
- expose enough metadata for budget and overflow enforcement in later slices

## Verification

- `make proto`
- `make swift-test`

## Acceptance

- adaptive-thinking configuration is represented in control-plane state
- effective adaptive behavior is observable and test-covered
