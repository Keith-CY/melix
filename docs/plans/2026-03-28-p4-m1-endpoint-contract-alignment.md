# P4-M1 Endpoint Contract Alignment

## Goal

Define one stable internal text-request contract for `POST /v1/chat/completions`, `POST /v1/completions`, `POST /v1/responses`, and `POST /v1/messages` before widening the public HTTP surface.

## Scope

- Add request models for completions, responses, and messages.
- Add response or stream envelope models needed to lock public discriminators.
- Introduce a normalization step that maps endpoint-specific requests onto one internal text-request shape.
- Preserve the current `chat/completions` translation path by implementing it on top of the same normalization flow.
- Add translator-level tests for endpoint equivalence, recovery metadata, and contract encoding.

## Non-Goals

- Make the new endpoints live in the HTTP gateway.
- Change SSE transport behavior beyond defining shared contract shapes.
- Add reasoning or tool-call delta formatting.
- Change the worker runtime or scheduler behavior.

## Implementation Notes

- Keep endpoint-specific behavior in request or response contracts and normalization.
- Keep worker routing, cache hints, and session metadata owned by the shared normalized request.
- Avoid introducing endpoint-specific runtime code paths in the worker request model.

## Performance Probes

- `http.completions_translation_ms`
- `http.responses_translation_ms`
- `http.messages_translation_ms`
- `http.translation_contract_equivalence_failures`

## Verification

- `swift test --package-path services/control-plane-swift --filter TextEndpointContractTests`
- `swift test --package-path services/control-plane-swift --filter OpenAIHandlerTests`
- `git diff --check`

## Acceptance

- Equivalent text prompts from the four endpoint families normalize into one internal request shape.
- Recovery and cache metadata survive normalization and translation.
- Response contract types expose stable public discriminator fields for later handler work.
