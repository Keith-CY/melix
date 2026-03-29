# P7-M1 Image Job Contracts Implementation Plan

**Goal:** Land the first Phase 7 slice by replacing the old synchronous image response shape with job-oriented image contracts, artifact metadata, and explicit cancellation semantics, then make the control plane able to represent queued, running, canceled, failed, and completed image jobs in snapshots and events.

**Architecture:** This slice is schema-first plus control-plane state modeling. It does not yet implement live image generation or editing, but it defines the worker and control-plane contracts that later image workers, HTTP handlers, and desktop panels will consume.

**Tech Stack:** Protocol Buffers, SwiftProtobuf, Python protobuf generation, Swift XCTest, Python pytest.

## Non-Goals

- Implement `POST /v1/images/generations` or `POST /v1/images/edits`.
- Build the native Image panel.
- Materialize image artifacts on disk or wire live image workers into the control plane.
- Add image-job metrics reports beyond the structural fields needed by later milestones.

## Context

- Relevant specs:
  - `docs/architecture-spec.md`
  - `docs/worker-rpc-schema.md`
  - `docs/control-plane-protocol.md`
  - `docs/plans/2026-03-27-phase-7-image-generation-editing.md`
  - `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
- Relevant code paths:
  - `packages/protocol/schema/worker/v1/common.proto`
  - `packages/protocol/schema/worker/v1/inference.proto`
  - `packages/protocol/schema/controlplane/v1/control_plane.proto`
  - `services/control-plane-swift/Sources/ModelCatalog/*`
  - `services/control-plane-swift/Sources/Snapshots/*`
  - `services/control-plane-swift/Sources/XPCService/*`

## Assumptions

- Cancellation continues to use `CancelRequest.request_id`; image job contracts must make the image request identity and job identity explicit so later handlers can map cancellation correctly.
- This slice preserves backward-compatible field tags where practical by appending new fields instead of rewriting existing tags.
- Generated artifacts under `packages/protocol/swift` and `packages/protocol/python` remain committed outputs.

## Performance Probes and Metrics

Runtime image metrics remain out of scope for this milestone, but the contracts introduced here must leave room for later Phase 7 probes:

- `image.job_queue_wait_ms`
- `image.job_run_ms`
- `image.job_cancel_latency_ms`
- `image.job_artifact_publish_ms`
- `image.job_peak_memory_bytes`
- `scheduler.text_ttft_under_image_load_ms`

Metrics report for this slice:

- `N/A` for live runtime values because P7-M1 only lands contracts and state models
- required evidence is successful generation, compilation, and control-plane test coverage for the touched source

## Work Plan

### Task 1: Extend worker image contracts

**Objective**

Replace raw image-byte responses with job-oriented image response shapes.

**Files**

- `packages/protocol/schema/worker/v1/common.proto`
- `packages/protocol/schema/worker/v1/inference.proto`

**Implementation**

- add image-generation capability and route enums
- add image job state, artifact role, artifact metadata, and progress messages
- update image generate and image edit response messages to return job descriptors rather than only inline bytes
- keep request identity and explicit edit-source fields available for later cancellation and artifact lineage

### Task 2: Extend control-plane image job vocabulary

**Objective**

Make the control plane able to surface image jobs as first-class operator-visible state.

**Files**

- `packages/protocol/schema/controlplane/v1/control_plane.proto`
- `services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift`
- `services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift`

**Implementation**

- add image-job state, artifact, and summary messages to the control-plane protocol
- add an image event topic and image job state-change event payload
- surface image job summaries in the server snapshot
- add the Phase 7 image model route and default queue lanes

### Task 3: Add a control-plane image job read model

**Objective**

Provide a testable state model for queued, running, canceled, failed, and completed image jobs before live worker integration lands.

**Files**

- `services/control-plane-swift/Sources/ImageJobs/*`
- `services/control-plane-swift/Tests/ControlPlaneTests/*`

**Implementation**

- add an `ImageJobReadModel` actor that records lifecycle transitions and produces stable summaries
- publish image job state-change events through the same event-hub conventions used elsewhere in the control plane
- keep the API narrow so later HTTP handlers and image workers can adopt it without rewrites

### Task 4: Regenerate artifacts and add protocol/state tests

**Objective**

Prove the new image job contracts compile and are representable from the control plane.

**Files**

- `packages/protocol/swift/**/*`
- `packages/protocol/python/**/*`
- `services/control-plane-swift/Tests/**/*`
- `services/mlx-worker-python/tests/**/*`
- `services/mlx-text-worker-swift/Tests/**/*`

**Implementation**

- regenerate Swift and Python protocol outputs
- add tests for image job contract fields and route typing
- add control-plane tests covering queued, running, canceled, failed, and completed image jobs
- keep the existing image RPC placeholders compiling against the new response shapes

## Verification

```bash
make proto
make swift-test
make py-test
make integration-test
make coverage
git diff --check
```

## Acceptance

- generated Swift and Python artifacts compile with the new Phase 7 image job vocabulary
- the control plane can represent queued, running, canceled, failed, and completed image jobs in tests
- default snapshots expose Phase 7 image lanes and image-capable model routing
- touched non-generated source stays at or above `95%` measured coverage
