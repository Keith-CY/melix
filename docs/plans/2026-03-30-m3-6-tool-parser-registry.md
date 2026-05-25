# M3.6 Tool Parser Registry

## Goal

Introduce a parser registry that supports multiple tool-call wire formats through one shared parsing interface.

## Scope

- define parser registration and selection
- support parser-family metadata at model and request levels
- keep parser choice observable for debugging and metrics

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/HTTPGateway/SSE/`
- update `services/mlx-worker-python/worker/registry.py`

## Implementation Notes

- registry-driven parser selection should replace hardcoded parser assumptions
- parser metadata should compose with model settings and request overrides
- keep the parser API general enough for both text and vision-family tool calls

## Issue #1524 Parser Audit Addendum

Every registered parser must publish an audit receipt so selector behavior can
be inspected without re-running parser execution. The receipt fields are:

- `parser_id`
- `parser_kind`
- `accepted_wire_formats`
- `selector_surface`
- `selector_source`
- `request_context_mode`
- `exemption_reason`

The registry owns `parser_id`, `parser_kind`, accepted wire formats, and the
supported request-context modes for each parser. Selector parity is audited
across the API request field, desktop tooling settings, and CLI reporting. API
and desktop surfaces must expose the same parser IDs and request-context modes.
The CLI surface may carry an exemption because it does not construct local
requests with a tool-parser selector; it reports remote
`supported_parsers` capability metadata instead.

The required request-context fixtures cover JSON structured output,
tool-call parsing, reasoning-aware parsing, and plain text. A parser that
supports multiple request contexts, such as `qwen` for tool-call and reasoning
output, must appear in selector receipts for each context on every selector
surface.

This audit slice only makes parser metadata and selector parity testable.
Behavior fixes for structured streaming and parser recovery remain covered by
#615 and #868 and should not be recreated here.

## Verification

- `make proto`
- `make swift-test`

## Acceptance

- multiple tool-call parsers can be selected through one shared registry
- parser choice is exposed in control-plane or runtime metadata
