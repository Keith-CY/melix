# P7-M5 Native Image Panel

**Goal:** Add a native SwiftUI Image panel that submits image-generation and image-edit jobs through the control plane, renders operator-visible job progress, and previews local artifacts without bypassing control-plane state.

**Scope:** This milestone covers control-plane XPC image commands, menu bar image-panel state and views, artifact preview wiring, and desktop-focused verification. It does not add image-job cancellation hardening or queue-isolation work; that remains `P7-M6`.

## Design Notes

- The desktop app remains a control-plane client and does not call local HTTP image endpoints directly.
- Image submissions should return typed control-plane job summaries and rely on follow-up snapshot or event updates for lifecycle truth.
- Artifact preview uses local file references already surfaced in control-plane metadata.
- The desktop app should expose both generation and edit flows with minimal operator input surfaces:
  - model selection
  - prompt
  - edit source URI
  - optional mask URI
  - size
  - variant count

## Work Plan

### Task 1: Extend the control-plane protocol for image commands

**Files**

- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
- Regenerate: `packages/protocol/swift/**/*`
- Regenerate: `packages/protocol/python/**/*`

**Implementation**

- Add typed `image.generate` and `image.edit` commands and replies.
- Keep job lifecycle truth in `ImageJobSummary`.
- Avoid introducing desktop-only payloads or side channels.

**Verification**

- `make proto`

### Task 2: Implement image execute paths in the control-plane service and XPC client

**Files**

- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/XPCClient/ControlPlaneXPCClient.swift`
- Modify related tests under:
  - `services/control-plane-swift/Tests/ControlPlaneTests`
  - `apps/macos-menubar/Tests/MenuBarTests`

**Implementation**

- Route image generate and edit commands through the image worker route.
- Update the image-job read model before and after worker execution.
- Surface typed errors for unknown models, unavailable workers, and invalid edit payloads.

**Verification**

- `make swift-test`

### Task 3: Add Image panel state, views, and artifact preview handling

**Files**

- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`
- Create or modify: `apps/macos-menubar/Sources/AppMain/Image/*`
- Modify related tests under `apps/macos-menubar/Tests/MenuBarTests`

**Implementation**

- Add Image tab UI for generation and edit submission.
- Render image-job progress and terminal state from control-plane snapshots and events.
- Surface artifact previews from local `storage_uri` metadata.

**Verification**

- `make swift-test`

### Task 4: Land desktop evidence and metrics reporting

**Files**

- Modify: `docs/README.md`
- Modify or create supporting tests and metrics evidence as needed

**Implementation**

- Add the P7-M5 plan to the docs index.
- Report desktop image-panel latency metrics for the changed scope.

**Verification**

- `make swift-test`
- `git diff --check`

## Metrics

Required metrics for this milestone:

- `desktop.image_action_latency_ms`
- `desktop.image_refresh_ms`

If live artifact-preview timing is not yet independently measurable, record it as `N/A` and state why.
