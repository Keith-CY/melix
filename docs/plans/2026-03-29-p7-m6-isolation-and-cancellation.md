# P7-M6 Isolation and Cancellation

**Goal:** Make Phase 7 image jobs queue behind an explicit control-plane admission boundary, harden queued and running cancellation paths, and expose queue-pressure metrics so image traffic does not silently degrade text responsiveness.

**Scope:** This milestone covers image-job admission control in the Swift control plane, cancellation wiring for desktop and operator flows, queue-pressure metrics, and verification for queued and running image work. It does not add final Phase 7 benchmark and operator evidence packaging; that remains `P7-M7`.

## Design Notes

- Image traffic must stay isolated behind a dedicated admission controller rather than sharing text decode scheduling state directly.
- Queued image jobs must be cancellable before a worker ever receives the request.
- Running image jobs must route cancellation through the existing worker abort path and preserve image-job terminal-state truth in the control plane.
- HTTP and XPC image entrypoints should share the same image admission controller in the live bootstrap path so queue pressure and cancellation remain coherent.
- Queue pressure should be measurable through stable metrics:
  - `images.active_jobs`
  - `images.queue_depth`
  - `images.queue_backpressure`
  - `images.queue_wait_ms`
  - `images.cancel_requested_total`
  - `images.cancel_success_total`
  - `images.rejected_requests`

## Work Plan

### Task 1: Add explicit image-job admission control

**Files**

- Create: `services/control-plane-swift/Sources/ImageJobs/ImageJobAdmissionController.swift`
- Modify related tests under `services/control-plane-swift/Tests/ControlPlaneTests`

**Implementation**

- Add an actor that serializes image-job admission with configurable active and queued limits.
- Record queued, admitted, rejected, and terminal state transitions through the scheduler read model when available.
- Update queue-pressure metrics whenever active or queued image-job counts change.

**Verification**

- `swift test --package-path services/control-plane-swift --filter ImageJobAdmissionControllerTests`

### Task 2: Route image admission and cancellation through the control plane

**Files**

- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- Modify: `services/control-plane-swift/Sources/Bootstrap/main.swift`
- Modify related tests under:
  - `services/control-plane-swift/Tests/ControlPlaneTests`
  - `services/control-plane-swift/Tests/HTTPGatewayTests`

**Implementation**

- Gate image generate and image edit requests behind the shared admission controller.
- Reject saturated image queues with typed `resource_exhausted` responses.
- Add `ops.cancel_request` coverage for queued and running image jobs.
- Ensure live bootstrap shares one admission controller between HTTP and XPC surfaces.

**Verification**

- `swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests`
- `swift test --package-path services/control-plane-swift --filter OpenAIHandlerTests`

### Task 3: Surface cancellation from the native desktop image panel

**Files**

- Modify: `apps/macos-menubar/Sources/AppMain/XPCClient/ControlPlaneXPCClient.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Image/DesktopImageView.swift`
- Modify related tests under `apps/macos-menubar/Tests/MenuBarTests`

**Implementation**

- Add an explicit image-job cancel request on the XPC client.
- Surface cancel affordances only for cancelable image jobs in the desktop Image panel.
- Record desktop-side cancellation latency metrics.

**Verification**

- `swift test --package-path apps/macos-menubar`

### Task 4: Record docs and verification evidence

**Files**

- Modify: `docs/README.md`

**Implementation**

- Add the P7-M6 plan to the docs index.
- Keep the milestone metrics report focused on cancellation reliability and queue pressure.

**Verification**

- `git diff --check`

## Metrics

Required metrics for this milestone:

- `images.active_jobs`
- `images.queue_depth`
- `images.queue_backpressure`
- `images.queue_wait_ms`
- `images.cancel_requested_total`
- `images.cancel_success_total`
- `desktop.image_cancel_latency_ms`

If image-versus-text isolation is not yet benchmarked under mixed load in this milestone, record the cross-runtime latency comparison as `N/A` and state that final operator evidence is deferred to `P7-M7`.
