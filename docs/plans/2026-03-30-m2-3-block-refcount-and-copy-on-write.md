# M2.3 Block Refcount And Copy-On-Write

## Goal

Add per-block reference counting and copy-on-write semantics so reused cache blocks can be shared safely across requests and branches.

## Scope

- track block ownership and reference counts
- fork reused cache state through copy-on-write instead of destructive mutation
- keep branch and recovery flows compatible with the shared-block model

## Files

- update `services/mlx-text-worker-swift/Sources/Core/`
- update `services/control-plane-swift/Sources/Snapshots/`
- update `tests/integration/test_recovery_flows.py`

## Implementation Notes

- shared blocks must be safe under concurrent request and restore activity
- block-level ownership should compose with branch-aware snapshot semantics
- metrics should distinguish shared reuse from copy-on-write forks

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- reused blocks can be shared safely across compatible requests
- branch or restore mutations trigger copy-on-write rather than destructive reuse
