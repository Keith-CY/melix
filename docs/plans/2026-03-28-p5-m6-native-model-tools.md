# P5-M6 Native Model Tools Implementation Plan

## Goal

Make the native SwiftUI desktop shell drive real Phase 5 model-operations behavior through the control plane.

This milestone must let operators:

- inspect model metadata and current settings
- update per-model settings from the desktop shell
- trigger quantize, download, and upload jobs from native desktop workflows
- observe the latest operation result without leaving the app

## Non-Goals

- Do not add training or adapter workflows in this milestone.
- Do not add HuggingFace authentication UX beyond deterministic target-repo inputs.
- Do not add remote transport or network sync beyond the existing local control-plane path.
- Do not add Phase 7 image workflows or Phase 6 chat-panel workflows here.

## Context

Phase 5 already includes:

- typed model capability routing and per-model settings fields
- Python maintenance jobs for quantize, download, and upload operations
- control-plane endpoint routing for embeddings, rerank, health, and cache stats

The missing layer is the desktop operator workflow. The menu bar shell must now use real control-plane commands instead of placeholder read-only rows.

Canonical references:

- `docs/architecture-spec.md`
- `docs/plans/2026-03-27-phase-5-embeddings-rerank.md`
- `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`

## Assumptions and Defaults

- The desktop shell remains a native SwiftUI app.
- `packages/protocol/schema/controlplane/v1/control_plane.proto` remains the source of truth for new desktop-facing control-plane commands.
- Model settings updates remain control-plane mutations against `ModelCatalog`.
- Model-operation jobs remain Python maintenance jobs routed through the model-operations worker client.
- The first native tools workflow is synchronous at the control-plane command boundary: the desktop app waits for the operation to finish and then renders the result.

## Performance Probes

- `desktop.model_settings_ms`
- `desktop.model_info_ms`
- `desktop.model_operation_ms`
- `control_plane.model_settings_ms`
- `control_plane.model_operation_ms`

## Work Plan

### Task 1: Extend control-plane protocol shapes for native model tools

**Objective**

Add typed command and reply payloads for model metadata, settings updates, and model-operation runs.

**Files**

- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
- Regenerate: `packages/protocol/swift/*`
- Regenerate: `packages/protocol/python/*`

**Implementation**

- Add a model-info command and reply shape.
- Add a typed model-operation command and result shape covering `quantize`, `download`, and `upload`.
- Keep the command family under `ModelCommand` so the desktop shell can stay model-centric.

**Verification**

- `make proto`
- `swift build --package-path packages/protocol/swift`

### Task 2: Implement control-plane execution and local XPC client support

**Objective**

Make the control plane execute native model-tool commands through `ModelCatalog` and the Python model-operations worker.

**Files**

- Modify: `services/control-plane-swift/Sources/XPCService/*`
- Modify: `services/control-plane-swift/Sources/WorkerClient/*`
- Modify: `services/control-plane-swift/Sources/Bootstrap/*`
- Modify tests under `services/control-plane-swift/Tests`
- Modify: `apps/macos-menubar/Sources/AppMain/XPCClient/*`
- Modify tests under `apps/macos-menubar/Tests/MenuBarTests`

**Implementation**

- Handle model settings mutations through `ModelCatalog.updateSettings`.
- Route model-info and model-operation commands through the model-operations worker client.
- Return typed results suitable for the native desktop shell.
- Extend the local XPC client protocol with these new operations.

**Verification**

- `make swift-test`

### Task 3: Add native Models and Tools workflows to the desktop shell

**Objective**

Turn the current read-mostly desktop shell into an operator workflow for model settings and Phase 5 maintenance jobs.

**Files**

- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/*`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/*`
- Modify tests under `apps/macos-menubar/Tests/MenuBarTests`

**Implementation**

- Add a `Tools` tab beside the existing dashboard foundation tabs.
- Extend the `Models` tab to show alias, memory policy, acceleration mode, and supported features.
- Add native actions for settings update, quantize, download, and upload.
- Show the latest operation result and surface failures through the existing error/log state.

**Verification**

- `make swift-test`

### Task 4: Add operator verification and metrics evidence

**Objective**

Leave `P5-M6` with reproducible evidence for desktop-driven model settings and model-operation jobs.

**Files**

- Modify: `scripts/phase5_control_plane_metrics.py`
- Modify: `README.md`
- Modify or create tests under `tests/integration`

**Implementation**

- Add one operator smoke path that updates settings and runs at least one model-operation job through the desktop-facing control-plane path.
- Record native workflow metrics in the Phase 5 report.

**Verification**

- `make swift-test`
- `make py-test`
- `make integration-test`
- `make coverage`
- `make phase5-metrics`

## Acceptance

- The desktop `Models` workflow can update settings through the control plane.
- The desktop `Tools` workflow can run quantize, download, and upload jobs through the control plane.
- The native shell renders typed result state for the last model-operation run.
- The touched repository scope remains at or above `95%` measured coverage.
- The Phase 5 metrics report includes non-`N/A` desktop or control-plane model-tools timings.

## Rollback and Safe Exit

- If model-operation commands are not stable, keep the `Tools` tab hidden and retain the protocol additions behind non-executed paths.
- If settings update support is stable but long-running jobs are not, ship only settings mutation in this milestone and leave job execution to the next slice.
