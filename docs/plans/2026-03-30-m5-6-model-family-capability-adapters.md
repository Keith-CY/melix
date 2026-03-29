# M5.6 Model-Family Capability Adapters

## Goal

Add capability adapters for the requested model families so routing, parser selection, and modality declarations are family-aware.

## Scope

- define adapter boundaries for requested family groups
- expose modality, task, and parser capabilities by family
- preserve one control-plane routing model across families

## Files

- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/WorkerClient/WorkerRegistry.swift`
- update `tests/integration/`

## Implementation Notes

- adapters should own family-specific capability declarations instead of scattering them across the control plane
- the control plane should consume family capability metadata, not hardcode family names
- keep family support incremental and testable

## Verification

- `make py-test`
- `make swift-test`
- `make integration-test`

## Acceptance

- requested model families can be represented through capability adapters
- routing and parser selection respect family-specific capability metadata
