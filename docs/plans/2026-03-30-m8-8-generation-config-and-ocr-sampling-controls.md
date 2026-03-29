# M8.8 Generation Config And OCR Sampling Controls

## Goal

Import generation-config defaults where available and expose OCR-specific sampling controls without fragmenting the shared settings model.

## Scope

- load and merge generation-config defaults
- expose OCR-specific sampling controls
- preserve explicit override precedence

## Files

- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `tests/integration/`

## Implementation Notes

- generation-config import should remain non-destructive and inspectable
- OCR sampling controls should integrate with the shared settings model rather than bypass it
- keep precedence rules explicit and testable

## Verification

- `make py-test`
- `make swift-test`
- `make integration-test`

## Acceptance

- generation-config defaults can be loaded and merged
- OCR sampling controls are operator-visible and test-covered
