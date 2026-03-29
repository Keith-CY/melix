# M9.2 Agent Integration Exports

## Goal

Provide integration and export paths for external coding-agent tools, including `OpenClaw`, `Hermes Agent`, `OpenCode`, and `Codex`.

## Scope

- define exportable integration artifacts or settings
- keep integrations operator-visible and reproducible
- preserve one Melix runtime identity across tool-specific exports

## Files

- update `apps/macos-menubar/Sources/AppMain/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `docs/runbooks/`
- update `README.md`

## Implementation Notes

- tool-specific exports should remain data-driven rather than hardcoded view-only text
- keep integration guidance consistent with supported local API and tool surfaces
- avoid silent divergence between exported settings and actual runtime behavior

## Verification

- integration-export smoke command for the touched scope
- `make swift-test`

## Acceptance

- Melix can export or surface integration material for the supported coding-agent tools
- the exported material is reproducible and product-owned
