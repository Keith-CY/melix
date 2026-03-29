# P8-M3 Adapter and Training Product Tooling

## Goal

Turn Phase 8 model-tooling from single-action buttons into backend-backed product state by exposing adapter registry data, training history, and publish-aware controls in the native desktop shell.

## Scope

- add a backend-readable model-operations registry snapshot in the Python maintenance path
- derive adapter package rows and training-history rows from real backend state
- hydrate native desktop tooling state from the registry snapshot rather than placeholder labels
- expose refresh and adapter publish controls that operate on backend-provided adapter metadata

## Non-Goals

- add full training orchestration beyond the existing LoRA entrypoint
- introduce a new public protocol surface for model-ops history
- add packaging, signing, or startup automation work from later Phase 8 milestones

## Files

- `services/mlx-worker-python/worker/model_ops/job_registry.py`
- `services/mlx-worker-python/worker/engine/maintenance_core.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`
- `apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`
- `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`

## Design

### Backend Registry Snapshot

- Reuse the existing model-operations request path with a `registry_snapshot` operation.
- Keep the request within the current maintenance service and return a manifest payload that contains:
  - ordered job history
  - derived adapter package registry
  - publish metadata inferred from adapter upload receipts
- Exclude the snapshot job itself from the emitted history so the operator view reflects real tooling work only.

### Native Product State

- Add adapter package state and training-history state to the runtime view model.
- Parse registry snapshot manifests into typed desktop rows.
- Refresh the tooling state explicitly from the desktop shell and automatically after training or adapter publish actions.

### Product Controls

- Add a tooling refresh action.
- Add a publish-latest-adapter action that uses backend-derived adapter metadata, including target repository and artifact path.
- Keep the control plane as the orchestration source; the desktop shell remains a projection of backend state.

## Performance Probes

- `menu.model_ops_refresh_ms`
- existing `menu.model_operation_ms`
- existing `training.job_duration_ms`
- existing `training.adapter_publish_ms`

## Verification

```bash
make swift-test
make py-test
make integration-test
make coverage
```

## Acceptance

- backend model-ops state can be queried as a registry snapshot without adding a new public protocol
- adapter registry rows and training-history rows shown in the native shell are sourced from backend manifests
- the publish-adapter control operates on backend-derived adapter metadata instead of hard-coded placeholders
- touched-scope automated coverage remains at or above `95%`
