# M9.4 Persistent Sessions And Remember-Me

## Goal

Add persistent session support and remember-me behavior so authenticated operator access can survive restarts where product policy allows it.

## Scope

- define persistent session storage
- add remember-me policy and retention behavior
- keep session state compatible with local product constraints

## Files

- update `services/control-plane-swift/Sources/HTTPGateway/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `docs/runbooks/`
- update `tests/integration/`

## Implementation Notes

- session persistence should remain explicit and configurable
- retention policy should be visible to operators
- keep persistent sessions separate from model session-graph semantics

## Verification

- `make swift-test`
- persistent-session smoke command for the touched scope

## Acceptance

- Melix can persist authenticated sessions where enabled
- remember-me behavior is explicit and test-covered
