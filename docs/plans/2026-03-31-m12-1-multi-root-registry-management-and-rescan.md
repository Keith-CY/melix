# M12.1 Multi-Root Registry Management And Rescan

## Status

In progress on 2026-04-05. The current repository can discover registry roots from
`MELIX_MODEL_ROOTS` and emit snapshot payloads, but root configuration is still environment-owned,
root identity is index-derived, and there is no operator-facing add, remove, reorder, or rescan
surface. This slice closes that gap by making root configuration control-plane-owned, root
identity stable, and rescans explicit across worker snapshots, catalog sync, and Window UI
actions.

## Goal

Complete the operator-facing management layer for multiple model roots, ordered scanning, and rescan behavior.

## Scope

- add root add, remove, reorder, and rescan semantics
- keep root identity and scan results observable
- preserve deterministic provider and variant discovery

## Files

- update `services/mlx-worker-python/worker/model_registry/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `docs/runbooks/`

## Implementation Notes

- Root ordering should remain explicit and testable.
- Invalid roots must not poison the full registry snapshot.
- Rescan behavior should preserve existing sidecar-override semantics.

## Verification

- `make py-test`
- `make swift-test`

## Acceptance

- Operators can manage multiple roots and trigger rescans deterministically.
- Registry identity remains stable across rescan cycles.
