# M9.5 Rich Output Sanitization

## Goal

Sanitize rendered rich output so operator-facing surfaces do not expose unsafe HTML-capable rendering paths.

## Scope

- add sanitization for rich rendered output
- preserve legitimate formatting where allowed
- keep sanitization behavior visible and testable

## Files

- update `apps/macos-menubar/Sources/AppMain/`
- update `services/control-plane-swift/Sources/HTTPGateway/`
- update `docs/runbooks/`
- update `apps/macos-menubar/Tests/MenuBarTests/`

## Implementation Notes

- sanitization should be explicit at the rendering boundary
- preserve operator-visible fidelity where safe, but default to safety
- keep sanitization rules versioned and testable

## Verification

- `make swift-test`
- sanitization smoke command for the touched scope

## Acceptance

- rich output is sanitized before rendering on supported surfaces
- unsafe output cases are test-covered
