# P4-M6 Native Desktop Foundation Implementation Plan

**Scope:** This milestone upgrades the macOS operator shell from a thin menu-only surface into a real native SwiftUI desktop foundation. The slice covers Dashboard, Models, Settings, Logs, Bench, and API reference views backed by control-plane truth that already exists in the current repository. It does not add chat, image, HuggingFace, quantization, training, or tool workflows that belong to later phases.

**Goal:** Leave Phase 4 with a real native desktop console that renders server snapshot truth, model state, queue and cache summaries, benchmark-facing metrics, and local endpoint reference material from the current control-plane contract while preserving the existing menu bar operator flow.

**Performance probes for this milestone**

- `menu.console_open_ms`
- `menu.foundation_refresh_ms`
- `menu.handshake_ms`
- `menu.hydration_ms`
- `menu.model_load_ms`
- `menu.model_unload_ms`

The metrics report for this milestone must include non-`N/A` desktop interaction evidence for open, refresh, and snapshot-driven hydration.

## Context

- Canonical phase plan: `docs/plans/2026-03-27-phase-4-text-api-breadth-agent-semantics.md`
- Milestone ladder: `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
- Relevant code:
  - `apps/macos-menubar/Sources/AppMain/*`
  - `services/control-plane-swift/Sources/XPCService/*`
  - `services/control-plane-swift/Sources/Snapshots/*`

## Non-Goals

- Build the native Chat panel.
- Build the native Image panel.
- Expose placeholder tabs for model upload, download, quantization, training, or cache inspection before their backend phases.
- Introduce worker-direct transport from the app.
- Replace the menu bar shell with a full document-style app lifecycle.

## Implementation Plan

### Task 1: Expand the app-side control-plane client for foundation refresh

**Objective**

Let the desktop app request fresh server snapshot truth on demand instead of relying only on launch hydration.

**Files**

- Modify: `apps/macos-menubar/Sources/AppMain/XPCClient/ControlPlaneXPCClient.swift`
- Modify tests under `apps/macos-menubar/Tests/MenuBarTests`

**Implementation**

- Add snapshot-refresh support to the app-side XPC client abstraction.
- Keep the client aligned with existing control-plane commands rather than adding app-specific transport.

**Acceptance**

- The app can request a fresh `ServerSnapshot` without bypassing the control plane.

### Task 2: Add a desktop-foundation state model on top of control-plane truth

**Objective**

Turn the raw snapshot, event stream, and handshake metadata into stable desktop panel state.

**Files**

- Create: `apps/macos-menubar/Sources/AppMain/Dashboard/*`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`

**Implementation**

- Add desktop panel state for Dashboard, Models, Settings, Logs, Bench, and API reference.
- Keep state derivation deterministic and testable.
- Use only current control-plane truth:
  - server state
  - model summaries
  - queue summary
  - cache summary
  - metrics summary
  - session summaries
  - recent errors and event feed

**Acceptance**

- The desktop foundation can render all required sections from the current control-plane model without hidden app-only state.

### Task 3: Add a real SwiftUI desktop console and presenter

**Objective**

Provide a real native desktop window that the menu bar shell can open on demand.

**Files**

- Create: `apps/macos-menubar/Sources/AppMain/Dashboard/*`
- Modify: `apps/macos-menubar/Sources/AppMain/AppMain.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/MenuBar/StatusMenu.swift`

**Implementation**

- Add a SwiftUI root view for the desktop foundation.
- Add a presenter that opens or reuses a single native console window.
- Wire the status menu to expose an `Open Melix Console` action.

**Acceptance**

- The menu bar app can open a real native desktop foundation window.

### Task 4: Verify the desktop foundation and metrics evidence

**Objective**

Finish the milestone with reproducible desktop-state and operator-action coverage.

**Files**

- Modify tests under `apps/macos-menubar/Tests/MenuBarTests`
- Update docs only if verification commands or operator notes change

**Implementation**

- Add tests for:
  - foundation hydration
  - foundation refresh
  - open-console action routing
  - presenter reuse behavior
  - API reference and bench state derivation
- Keep touched-scope automated coverage at or above `95%`.

**Verification**

- `swift test --package-path apps/macos-menubar`
- `make swift-test`
- `make coverage`

**Acceptance**

- The native desktop shell exposes real operator state rather than placeholder views.
- The touched scope meets the coverage gate.
- The milestone produces non-`N/A` desktop metrics evidence.

## Safe Exit

- Keep the existing menu-only operator path functional while the desktop foundation lands.
- If one panel proves unstable, keep the shared state model and defer only the unstable panel view instead of backing out the whole foundation.
