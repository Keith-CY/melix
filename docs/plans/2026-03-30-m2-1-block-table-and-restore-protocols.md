# M2.1 Block Table And Restore Protocols

## Goal

Define the protocol shapes needed for paged cache ownership, block-aware restore, and boundary-aware recovery planning.

## Scope

- add block and page identities to worker and control-plane contracts
- define restore-plan and restore-boundary metadata
- keep current snapshot semantics compatible during migration

## Files

- update `packages/protocol/schema/worker/v1/`
- update `packages/protocol/schema/controlplane/v1/`
- update `services/control-plane-swift/Sources/Snapshots/`
- update `services/mlx-text-worker-swift/Sources/Core/`

## Implementation Notes

- the protocol must support partial restore and future VLM reuse without text-only assumptions
- restore metadata should be structured rather than opaque strings
- preserve a clean bridge from legacy snapshot records into the new protocol

## Verification

- `make proto`
- `make swift-test`
- `make integration-test`

## Acceptance

- protocol schemas represent block tables, page references, and restore plans explicitly
- control-plane and worker tests can encode and decode the new restore metadata
