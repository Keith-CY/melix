# M3.5 JSON Mode And Schema Validation

## Goal

Introduce structured-output controls that can enforce JSON-only output and validate output against JSON Schema where requested.

## Scope

- add JSON mode request semantics
- add JSON Schema validation hooks
- keep validation failures explicit and operator-visible

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/HTTPGateway/OpenAI/`
- update `services/control-plane-swift/Tests/ControlPlaneTests/`

## Implementation Notes

- validation should run after model output assembly and before final protocol framing where needed
- schema failures should produce structured errors rather than silent truncation
- keep JSON mode and tool-calling semantics compatible

## Verification

- `make proto`
- `make swift-test`
- `make integration-test`

## Acceptance

- JSON mode is requestable through the public API surface
- schema validation can pass or fail with explicit structured outcomes
