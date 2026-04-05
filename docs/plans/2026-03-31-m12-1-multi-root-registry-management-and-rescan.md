# M12.1 Multi-Root Registry Management And Rescan

## Status

Completed on 2026-04-05. The repository now treats registry-root configuration as
control-plane-owned state, projects stable root identity from canonical root paths, preserves
explicit empty-root overrides across sync cycles, and exposes add, remove, reorder, and rescan
actions through the Window UI and model-ops surface.

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

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_maintenance_service.py -q`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'ModelCatalogTests|ControlPlaneServiceTests'`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
- `git diff --check`

## Acceptance

- Operators can manage multiple roots and trigger rescans deterministically.
- Registry identity remains stable across rescan cycles.

## Completion Notes

- Worker-backed registry snapshots now surface stable `root_id`, ordered `root_order`, explicit
  root-path overrides, root-level accessibility, and discovered-model associations.
- Control-plane catalog state now persists configured root overrides, distinguishes explicit empty
  overrides from fallback environment discovery, and reapplies configured roots during follow-on
  sync operations.
- Window UI root management now supports add, remove, reorder, and rescan operations while
  preserving the latest registry-root snapshot and surfacing ordered root observability.
