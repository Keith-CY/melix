# M8.1 Multi-Root Model Registry

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
