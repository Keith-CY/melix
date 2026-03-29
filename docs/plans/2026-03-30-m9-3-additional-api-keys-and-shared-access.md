# M9.3 Additional API Keys And Shared Access

## Goal

Support additional API keys and shared-access patterns so one Melix runtime can be used safely by more than one client or operator context.

## Scope

- define additional API-key storage and validation
- support shared-access semantics
- keep local-trust shortcuts explicit rather than implicit

## Files

- update `services/control-plane-swift/Sources/HTTPGateway/OpenAI/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `docs/runbooks/`

## Implementation Notes

- shared access should remain explicit in policy and operator state
- key management should not compromise local-first startup and operator workflows
- preserve compatibility with existing localhost trust behavior where policy allows it

## Verification

- `make swift-test`
- shared-access smoke command for the touched scope

## Acceptance

- Melix can represent and validate multiple API keys where enabled
- shared-access behavior is explicit and test-covered
