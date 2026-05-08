# Engine Generate Token Accumulation Elision

## Goal

Reduce per-token bookkeeping in the Python text generation hot path by avoiding
`RequestState.emitted_tokens` accumulation during `EngineCore.generate(...)`.
The stream assembler is already the authoritative source for generated assistant
text in the generate path, so request-state token storage is redundant for this
path.

## Scope

- Keep generate streaming events, completed assistant text, and usage accounting
  semantically unchanged.
- Preserve decode behavior, where request-state token accumulation still backs
  completed assistant text.
- Extend the registered PR-scoped `engine-generate-usage-token-elision` probe to
  report request-state append calls per request.

## Verification

- Focused generate stream tests must prove generate output still completes with
  the same assistant text and usage tokens without calling
  `RequestState.append_token(...)`.
- Changed-scope coverage must include `engine_core.py`, the focused generate
  tests, the PR-scoped performance tests, and the probe script.
- The registered probe should show
  `request_state_append_calls_per_request=0` for the optimized generate path.
