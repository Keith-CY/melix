# M4.8 Vision Model-Family Adapters

## Goal

Add family adapters for broader vision-model support without baking family-specific behavior directly into the generic VLM runtime.

## Scope

- define adapter boundaries for vision-model families
- keep shared multimodal semantics above family-specific runtime details
- expose family capabilities and constraints to operators

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `tests/integration/`

## Implementation Notes

- adapters should own family-specific tokenization, prompt shaping, and capability declarations
- registry metadata should explain modality and task support clearly
- avoid a monolithic VLM runtime file that absorbs every family difference

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- broader vision-model families can be integrated through adapter boundaries
- capability declarations and integration behavior remain test-covered
