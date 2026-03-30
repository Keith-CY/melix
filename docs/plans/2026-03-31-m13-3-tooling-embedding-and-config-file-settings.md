# M13.3 Tooling, Embedding, And Config-File Settings

## Goal

Expose embedding-model selection, tool-parser settings, MCP configuration, config-file location, and additional-arguments handling through one coherent settings surface.

## Scope

- add embedding-model selection and preload settings
- expose tool-parser and MCP configuration
- expose config-file path and additional-arguments state

## Files

- update `services/control-plane-swift/Sources/XPCService/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `docs/runbooks/`

## Implementation Notes

- Config-file state should remain inspectable even when the current process inherited values at boot.
- MCP and parser settings should remain configuration-driven, not hardcoded in UI.
- Embedding selection must align with capability-aware model discovery.

## Verification

- `make swift-test`
- tooling-settings smoke command for the touched scope

## Acceptance

- Tooling, embedding, and config-file settings are visible, stable, and test-covered.
- Operators can inspect the effective settings path without reading source files.
