# M1.7 Enforcement Disable And Initial Cache Blocks

## Goal

Allow memory enforcement to be fully disabled when explicitly configured and make initial cache-block sizing a first-class runtime control.

## Scope

- add an explicit full-disable enforcement mode
- add configurable initial cache-block sizing
- document the interaction between enforcement, cache initialization, and residency behavior

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `packages/protocol/schema/worker/v1/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/mlx-text-worker-swift/Sources/Core/`
- update `services/mlx-worker-python/worker/registry.py`

## Implementation Notes

- enforcement disable should be explicit and easy to audit
- initial cache-block configuration should affect both cold-start and reload behavior
- configuration should remain compatible with future platform packaging flows

## Verification

- `make proto`
- `make swift-test`
- `make py-test`

## Acceptance

- operators can disable enforcement explicitly
- initial cache-block sizing is configurable and visible through runtime state or metrics
