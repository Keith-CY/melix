# M9.1 MCP Tool Loading And Auto-Injection

## Goal

Load MCP tool configuration into Melix and automatically inject supported tools into the available tool surface for local runtime consumers.

## Scope

- load MCP configuration
- expose MCP-derived tools as a supported tool source
- preserve explicit operator control over enabled tool sources

## Files

- update `services/control-plane-swift/Sources/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `docs/runbooks/`
- update `tests/integration/`

## Implementation Notes

- MCP loading should remain configuration-driven rather than hardcoded
- tool-source identity should stay explicit in operator state and metrics
- keep injection behavior compatible with the shared tool parser stack

## Verification

- `make swift-test`
- MCP configuration smoke command for the touched scope

## Acceptance

- Melix can load MCP configuration and surface MCP-backed tools explicitly
- MCP tool-source behavior is test-covered
