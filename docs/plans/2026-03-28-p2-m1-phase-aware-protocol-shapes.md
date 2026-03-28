# P2-M1 Phase-Aware Protocol Shapes Plan

**Goal:** Land the first Phase 2 slice by extending the shared worker and control-plane protocols so Melix can represent queued, admitted, prefill, decode, and terminal request phases together with acceleration-policy intent, without implementing scheduler or runtime behavior yet.

**Architecture:** This slice is schema-first. The shared protocol becomes expressive enough for later lane-aware scheduling, `Prefill` and `Decode`, speculative decode, accelerated prefill, and active-path KV-cache policy, while the current Phase 1 runtime behavior remains unchanged.

**Tech Stack:** Protocol Buffers, SwiftProtobuf, gRPC Swift stubs, Python protobuf generation, Swift XCTest.

## Non-Goals

- Implement live scheduler lanes or admission behavior.
- Implement worker-side `Prefill` or `Decode` execution.
- Change the public HTTP endpoint set.
- Add cache persistence or resume behavior beyond new protocol fields.

## Context

- Relevant specs:
  - `docs/architecture-spec.md`
  - `docs/control-plane-protocol.md`
  - `docs/worker-rpc-schema.md`
  - `docs/plans/2026-03-27-phase-2-text-runtime-depth.md`
  - `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
- Relevant code paths:
  - `packages/protocol/schema/controlplane/v1/control_plane.proto`
  - `packages/protocol/schema/worker/v1/common.proto`
  - `packages/protocol/schema/worker/v1/inference.proto`
  - `services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift`
  - `services/control-plane-swift/Tests/ControlPlaneTests`

## Assumptions

- Phase 1 remains the active runtime path while P2-M1 lands.
- This slice should preserve wire compatibility for existing Phase 1 code paths by appending fields rather than rewriting existing tags.
- Generated outputs under `packages/protocol/swift` and `packages/protocol/python` remain committed artifacts.

## Performance Probes and Metrics

This slice is protocol and representation work, so runtime acceleration metrics remain out of scope until later Phase 2 milestones.

Probe requirements introduced by the schema:

- `scheduler.admission_latency_ms`
- `scheduler.queue_delay_ms`
- `scheduler.active_lane_depth`
- `swift_text.prefill_ms`
- `swift_text.decode_ttft_ms`
- `swift_text.speculative_acceptance_rate`
- `swift_text.speculative_rollback_rate`
- `swift_text.active_kv_quantization_ratio`

Metrics report for this slice:

- `N/A` for live runtime values, because P2-M1 only establishes protocol and test representation
- required evidence is successful generation, compile, and control-plane test coverage for the touched source

## Work Plan

### Task 1: Extend worker protocol vocabulary

**Objective**

Add phase-aware and acceleration-aware worker protocol shapes without changing live Phase 1 semantics.

**Files**

- `packages/protocol/schema/worker/v1/common.proto`
- `packages/protocol/schema/worker/v1/inference.proto`

**Implementation**

- add explicit acceleration-policy fields to the shared execution metadata
- add worker-side lifecycle and admission enums for queued, admitted, prefill, decode, completed, aborted, and failed states
- enrich `PrefillRequest`, `PrefillResponse`, `DecodeRequest`, and `ExecuteEvent` with the minimum fields needed for later Phase 2 slices

### Task 2: Extend control-plane event and queue vocabulary

**Objective**

Make the control-plane event model capable of representing phase-aware request progress and scheduler intent.

**Files**

- `packages/protocol/schema/controlplane/v1/control_plane.proto`
- `services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift`

**Implementation**

- add admission-state and acceleration-mode fields to request progress
- make queue summaries use Phase 2 lane names rather than anonymous placeholders
- keep values zeroed until scheduler behavior lands in later milestones

### Task 3: Regenerate outputs and add representational tests

**Objective**

Prove the new vocabulary compiles and is usable from the control plane.

**Files**

- `packages/protocol/swift/**/*`
- `packages/protocol/python/**/*`
- `services/control-plane-swift/Tests/ControlPlaneTests/**/*`

**Implementation**

- regenerate Swift and Python protocol artifacts
- add tests that instantiate and publish control-plane request progress for queued, prefill, decode, and terminal states
- add tests that verify the snapshot builder advertises the new Phase 2 lane layout

## Verification

```bash
make proto
swift build --package-path packages/protocol/swift
make py-test
make swift-test
make coverage
```

## Acceptance

- generated Swift and Python artifacts compile with the new Phase 2 vocabulary
- control-plane tests can represent queued, admitted, prefill, decode, and terminal request phases
- default server snapshots expose Phase 2 lane identities even before real scheduling logic lands
- touched non-generated source stays at or above `95%` measured coverage
