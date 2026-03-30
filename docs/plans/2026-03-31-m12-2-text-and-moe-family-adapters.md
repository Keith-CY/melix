# M12.2 Text And MoE Family Adapters

## Goal

Add the text-family and MoE-family adapter coverage needed for expanded large-model compatibility.

## Scope

- add family adapters for larger text and MoE-oriented models
- carry family-specific capability declarations into routing
- keep adapter behavior testable and metadata-driven

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/model_registry/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `tests/integration/`

## Implementation Notes

- Family-specific attention, positional-encoding, and MoE behaviors should remain adapter-scoped.
- Capability metadata should drive routing and settings affordances.
- Unsupported subfamilies should fail explicitly instead of degrading silently.

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- Expanded text and MoE families can be scanned, loaded, and routed through adapter metadata.
- Integration checks cover the targeted family matrix.
