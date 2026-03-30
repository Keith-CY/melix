# M13 Gateway Configuration, Defaults, And API Onboarding

## Goal

Expose a complete local gateway-configuration surface, generation-defaults model, and API-onboarding material so Melix can be configured and consumed without undocumented settings or source-level discovery.

## Scope

- add gateway configuration viewing and editing
- expose generation, batching, and speculative-decoding defaults
- expose embedding-model, MCP, tool-parser, and config-file settings
- publish operator-visible API reference and quick-start onboarding material

## Coverage

- host, port, API key, served-model name, rate limit, timeout, log level, and CORS settings
- concurrent-processing, max-concurrent-sequence, prefill-batch-size, and completion-batch-size controls
- default max tokens, default temperature, default top-p, and stream interval
- speculative-decoding controls, including draft-model selection and `num-draft-tokens` policy
- embedding-model selection, built-in tool-parser settings, MCP configuration, config-file path, and additional arguments
- OpenAI, Anthropic, and Ollama endpoint reference plus curl, Python, and JavaScript quick-start snippets

## Execution Slices

- `M13.1` Gateway config state model and persistence
- `M13.2` Generation, batching, and speculative defaults
- `M13.3` Tooling, embedding, and config-file settings
- `M13.4` API reference and quick-start onboarding

## Files

- update `services/control-plane-swift/Sources/HTTPGateway/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `services/control-plane-swift/Sources/Requests/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `docs/README.md`
- update `docs/runbooks/`
- update `tests/integration/`

## Implementation Notes

- Settings precedence must remain explicit across packaged defaults, config files, and operator overrides.
- The API reference should describe only supported, live surfaces and should not advertise incomplete placeholder routes.
- Quick-start examples should stay synchronized with supported endpoint shapes and streaming behavior.
- Tool and MCP configuration should remain configuration-driven and inspectable instead of hidden behind implicit boot logic.

## Verification

- `make swift-test`
- `make integration-test`
- gateway-config smoke command for the touched scope

## Acceptance

- Gateway configuration is complete, operator-visible, and round-trippable through control-plane truth.
- Generation and speculative defaults are inspectable and test-covered.
- API onboarding material matches live supported endpoints and payloads.
