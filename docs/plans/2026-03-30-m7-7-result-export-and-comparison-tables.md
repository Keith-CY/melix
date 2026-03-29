# M7.7 Result Export And Comparison Tables

## Goal

Allow benchmark and evaluation results to be exported in raw form and compared in operator-visible table views.

## Scope

- add raw JSON export
- add comparison-table generation
- preserve machine-readable and human-readable result views

## Files

- update `services/mlx-worker-python/worker/productization/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `docs/runbooks/`

## Implementation Notes

- export should preserve the underlying structured result model without lossy formatting
- comparison tables should operate on persisted results rather than transient UI state
- keep serving and evaluation results distinguishable in exports and tables

## Verification

- `make py-test`
- `make swift-test`
- export and comparison smoke command for touched scope

## Acceptance

- operators can export raw result data and inspect comparison tables
- export and comparison outputs remain consistent with stored benchmark results
