# M3.9 Reasoning Budgets And Overflow Closure

## Goal

Control reasoning output with explicit budgets and close thinking output safely when a request exceeds its configured reasoning allowance.

## Scope

- add model-level and request-level reasoning budgets
- expose effective reasoning-budget decisions in execution metadata
- force safe closure when the budget is exceeded

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/HTTPGateway/SSE/`
- update `services/control-plane-swift/Tests/ControlPlaneTests/`

## Implementation Notes

- budget enforcement should remain compatible with streaming deltas and completed outputs
- overflow closure should be explicit and machine-readable
- keep reasoning separation available for later endpoint-specific framing

## Verification

- `make proto`
- `make swift-test`
- `make integration-test`

## Acceptance

- reasoning budgets can be configured and enforced
- overflow closure behavior is explicit and test-covered
