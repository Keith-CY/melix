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

## Verification

- `make proto`
- `make swift-test`

## Acceptance

- multiple tool-call parsers can be selected through one shared registry
- parser choice is exposed in control-plane or runtime metadata
