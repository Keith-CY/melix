# M9.6 Connection Lifecycle Hardening

## Goal

Harden connection lifecycle behavior with explicit disconnect, retry, resume, and keepalive policy across long-running operator and API sessions.

## Scope

- define connection lifecycle policy
- keep disconnect and resume behavior observable
- preserve compatibility with existing streaming and heartbeat paths

## Files

- update `services/control-plane-swift/Sources/HTTPGateway/`
- update `services/control-plane-swift/Sources/Requests/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `tests/integration/`

## Implementation Notes

- lifecycle policy should distinguish transient and terminal failures
- resume behavior must not corrupt session, cache, or operator state
- keep keepalive semantics aligned across supported protocols

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- disconnect, retry, resume, and keepalive behavior are explicit and measurable
- lifecycle failure modes are integration-tested
