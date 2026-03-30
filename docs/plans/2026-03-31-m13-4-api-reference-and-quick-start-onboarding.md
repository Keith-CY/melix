# M13.4 API Reference And Quick-Start Onboarding

## Goal

Add product-owned API reference material and quick-start examples for supported local API consumers.

## Scope

- project supported endpoint reference from control-plane truth
- add curl, Python, and JavaScript quick-start examples
- keep onboarding aligned with supported OpenAI, Anthropic, and Ollama surfaces

## Files

- update `apps/macos-menubar/Sources/AppMain/`
- update `services/control-plane-swift/Sources/HTTPGateway/`
- update `docs/README.md`
- update `docs/runbooks/`

## Implementation Notes

- Reference material should describe only shipped or supported surfaces.
- Snippets should remain stable enough for automated smoke execution where practical.
- Onboarding should emphasize local endpoint behavior and auth expectations clearly.

## Verification

- `make swift-test`
- onboarding-example smoke command for the touched scope

## Acceptance

- API reference and quick-start material are product-visible, accurate, and maintainable.
- Example snippets match live endpoint behavior.
