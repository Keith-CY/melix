# M13.2 Generation, Batching, And Speculative Defaults

## Goal

Expose the generation, batching, and speculative-decoding defaults that shape serving behavior for the local gateway.

## Scope

- add default token and sampling controls
- expose batching and stream-interval settings
- add draft-model and `num-draft-tokens` configuration

## Files

- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/HTTPGateway/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/`

## Implementation Notes

- Defaults should remain separate from per-request overrides.
- Speculative settings must align with capability support and fail explicitly when unsupported.
- Effective values should remain visible after model-level merges.

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- Generation, batching, and speculative defaults are operator-visible and test-covered.
- Effective defaults are consistent across the gateway and desktop shell.
