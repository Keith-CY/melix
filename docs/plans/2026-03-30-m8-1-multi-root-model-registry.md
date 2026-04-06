# M8.1 Multi-Root Model Registry

## Status

Completed on 2026-04-04. Melix now discovers models from an ordered multi-root worker registry,
projects root identity and root order through worker-owned registry snapshots, synchronizes the
typed discovery results into the Swift control-plane catalog, and records the changed-line
coverage evidence for the touched Python and Swift scope in the backend-foundations implementation
plan.

## Goal

Implement an ordered multi-root model registry so Melix stops relying on scattered environment variables for model discovery.

## Scope

- define multi-root registry semantics
- preserve explicit overrides where needed
- keep registry behavior observable to operators

## Files

- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `docs/architecture-spec.md`

## Implementation Notes

- root ordering should be deterministic and explicit
- registry identity should remain compatible with provider, org, model, and variant metadata
- avoid mixing discovery policy with UI-only settings

## Verification

- `make py-test`
- `make swift-test`

## Acceptance

- Melix can discover models from multiple ordered roots
- registry behavior is explicit and test-covered
