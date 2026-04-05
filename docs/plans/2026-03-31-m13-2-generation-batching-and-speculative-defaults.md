# M13.2 Generation, Batching, And Speculative Defaults

## Goal

Expose the generation, batching, and speculative-decoding defaults that shape serving behavior for the local gateway.

## Scope

- add default token and sampling controls
- expose batching and stream-interval settings
- add draft-model and `num-draft-tokens` configuration
- keep timeout-default and rate-limit-adjacent serving behavior inspectable where it shapes request admission

## Implementation Slices

### Slice 1

Status: completed on 2026-04-05

- add a typed serving-defaults state model for gateway-level generation defaults
- persist operator defaults for `temperature`, `top_p`, `max_tokens`, and `stream_interval_tokens`
- project requested and effective generation defaults through `ServerSnapshot`
- route chat and completions request shaping through gateway defaults before request-level overrides
- migrate the existing Window UI advanced-default controls off desktop-only draft state

### Slice 2

- add batching and admission defaults including concurrent-processing and batch-size fields
- keep admission-shaping defaults visible beside timeout and rate-limit state
- surface effective batching defaults through the same snapshot path as generation defaults

### Slice 3

- add speculative-decoding defaults including draft-model selection and `num_draft_tokens`
- fail explicitly when speculative defaults target unsupported served models
- keep speculative effective state inspectable after model-level merges

## Files

- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/HTTPGateway/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/`

## Implementation Notes

- Defaults should remain separate from per-request overrides.
- Speculative settings must align with capability support and fail explicitly when unsupported.
- Effective values should remain visible after model-level merges.
- Serving defaults that influence admission or cancellation should stay visible beside sampling defaults, not buried in transport-only state.

## Key Probes

- `gateway.serving_defaults_apply_ms`
- `gateway.serving_defaults_persist_failures`
- `gateway.generation_default_merge_count`
- `gateway.speculative_config_apply_ms`

## Verification

- focused Swift tests for control-plane, HTTP gateway, and Window UI surfaces touched by the slice
- changed-line coverage for touched Swift files must be `>=95%`
- `make swift-test`
- `make integration-test`
- `git diff --check`

## Acceptance

- Generation, batching, and speculative defaults are operator-visible and test-covered.
- Effective defaults are consistent across the gateway and desktop shell.
- Adjacent serving defaults that shape request admission remain inspectable after settings merges.
