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

## Implementation Slice

- introduce shared capability metadata keys under `melix.capability.*` plus `melix.adapter_set_hash`
- emit embedding-family, rerank-family, and vision-family adapter metadata from the seeded model catalogs
- let the Swift catalog derive `routeClass`, `capabilityClass`, `supportedModalities`, and `supportedTasks` from adapter metadata
- let `WorkerRegistry` fall back to adapter metadata when explicit typed route metadata is absent
- let the Python maintenance path derive `supported_modalities`, `supported_tasks`, and `supported_parsers` from adapter metadata
- expose the default VLM family parser capability through model metadata so model-default parser selection is family-aware

## Measurement Points

- route resolution for summaries that carry only adapter metadata
- model-info capability reports for embedding, rerank, and VLM models
- model-default parser selection for the seeded VLM family

## Verification

- `make py-test`
- `make swift-test`
- `make integration-test`

## Acceptance

- requested model families can be represented through capability adapters
- routing and parser selection respect family-specific capability metadata
