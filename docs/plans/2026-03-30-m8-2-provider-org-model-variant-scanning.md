# M8.2 Provider, Org, Model, And Variant Scanning

## Goal

Scan models using a structured `provider/org/model/variant` hierarchy rather than one flat directory interpretation.

## Scope

- define the directory hierarchy interpretation
- add scanning and indexing for structured model trees
- expose discovered identity through model metadata

## Files

- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `docs/runbooks/`

## Implementation Notes

- sidecar manifests should override ambiguous path-derived metadata where needed
- scanning results should preserve provider and organization identity explicitly
- keep reload behavior safe when roots contain partial or invalid artifacts

## Verification

- `make py-test`
- `make swift-test`
- registry-scan smoke command for the touched scope

## Acceptance

- structured hierarchy scanning works across provider, organization, model, and variant layers
- discovered identity is operator-visible and test-covered
