# P3-M1 Cache and Session Contracts Implementation Plan

**Goal:** Land the first Phase 3 slice by making cache metadata, snapshot references, and session-graph state explicit and stable across the shared protocol family and the control-plane snapshot model, without yet implementing hot-tier persistence or restore execution.

**Scope:** This milestone covers protocol shape updates, generated artifact refresh, control-plane snapshot representation for cache and session metadata, and tests that prove the new shapes are visible through typed snapshots. It does not implement cache storage, checkpoint persistence, session mutation flows, or recovery scheduling.

## Context

- Phase plan: `docs/plans/2026-03-27-phase-3-cache-session-recovery.md`
- Milestone ladder: `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
- Canonical specs:
  - `docs/architecture-spec.md`
  - `docs/control-plane-protocol.md`
  - `docs/worker-rpc-schema.md`
- Relevant code:
  - `packages/protocol/schema/controlplane/v1/control_plane.proto`
  - `packages/protocol/schema/worker/v1/common.proto`
  - `packages/protocol/schema/worker/v1/cache.proto`
  - `services/control-plane-swift/Sources/Snapshots/*`
  - `services/control-plane-swift/Tests/ControlPlaneTests/*`

## Non-Goals

- Implement real cache persistence, block storage, or restore behavior.
- Add new public HTTP endpoints or desktop UI.
- Implement session creation, branch mutation, or tool-boundary recovery commands.
- Introduce worker-side cache ownership changes beyond contract vocabulary.

## Performance Probes

This milestone is contract-first and does not add a measurable hot path yet.

- Metrics report for commit: `N/A`
- Reason: the slice only adds protocol and representation support needed for later measurable Phase 3 cache and recovery work

## Work Plan

### Task 1: Expand shared cache and session vocabulary

- Add protocol messages for:
  - cache scope summaries
  - prefix refs
  - block-table refs and snapshot refs where missing
  - cache snapshot payloads for control-plane replies
  - richer session and branch metadata for summaries and full state
- Keep payload ownership in workers; only metadata becomes shared contract.

### Task 2: Refresh generated protocol artifacts

- Run `make proto`
- Refresh Swift and Python generated outputs for the new shapes
- Keep generated outputs committed and avoid hand edits

### Task 3: Make control-plane snapshots represent Phase 3 metadata

- Update the server snapshot builder so it can emit explicit empty or seeded cache metadata and explicit session summaries rather than placeholder gaps
- Keep defaults deterministic and lightweight
- Do not add live persistence yet

### Task 4: Add representational tests

- Add control-plane tests that assert:
  - handshake snapshots expose the new cache metadata shape
  - handshake snapshots expose session summaries
  - typed events or replies can carry session-state and cache-snapshot payloads without placeholder gaps
- Add protocol-generation verification to the standard commands

## Verification

```bash
make proto
swift build --package-path packages/protocol/swift
make swift-test
make py-test
make integration-test
make coverage
git diff --check
```

## Acceptance

- The shared protocol family exposes Phase 3 cache and session metadata needed for later worker and scheduler implementation
- The control-plane typed snapshot can represent cache and session graph state without placeholder-only gaps
- Generated artifacts remain aligned across Swift and Python
- Touched-scope automated coverage remains at or above `95%`

