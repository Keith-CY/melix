# P3-M5 Recovery Flows Implementation Plan

**Goal:** Turn the Phase 3 cache and session primitives into real recovery behavior by wiring snapshot restore and boundary-save flow through the Swift text worker and the control plane.

**Scope:** This milestone covers text-only recovery for the Swift text worker path. It activates worker-side restore or boundary-save semantics, session-aware control-plane routing, and integration evidence for restart-safe recovery.

**Non-Goals:**

- Add new public endpoint families beyond the existing chat path.
- Build a full cache inspector UI.
- Generalize recovery to Python workers or non-text families.
- Implement remote or multi-host cache restore.
- Add model-training, upload, or quantization workflows beyond the cache semantics they depend on.

## Context

- Canonical specs:
  - `docs/architecture-spec.md`
  - `docs/control-plane-protocol.md`
  - `docs/worker-rpc-schema.md`
  - `docs/plans/2026-03-27-phase-3-cache-session-recovery.md`
- Preceding milestone:
  - `docs/plans/2026-03-28-p3-m4-session-graph-state.md`
- Primary code paths:
  - `services/mlx-text-worker-swift/Sources/Core`
  - `services/control-plane-swift/Sources/Requests`
  - `services/control-plane-swift/Sources/WorkerClient`
  - `tests/integration`

## Assumptions

- The Swift text worker remains the default text execution engine.
- Recovery is carried over the existing worker protobuf surface rather than a new control-plane-only protocol.
- Session-tagged chat requests are allowed to carry Melix-specific optional fields for recovery metadata.
- Restart-aware recovery should be validated against the deterministic Swift backend first.

## Performance Probes

- `swift_text.cache_snapshot_save_ms`
- `swift_text.cache_snapshot_restore_ms`
- `swift_text.cache_l2_restore_hit_rate`
- `session_graph.request_hydration_ms`
- `session_graph.restore_snapshot_count`
- `session.followup_ttft_delta_ms`

## Work Plan

### 1. Activate worker-side restore-aware prefill

- Modify `services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift`
- Modify `services/mlx-text-worker-swift/Sources/Core/Inference/TextPrefillEngine.swift`
- When `execution.cache_hints.restore_snapshot_id` is present, prefill should rebuild a decode handle from the saved boundary snapshot instead of running a cold prefill.
- `PrefillResponse` must return the restored snapshot identifier and block-table metadata needed for the subsequent decode step.

### 2. Emit boundary-save recovery events during decode

- Modify `services/mlx-text-worker-swift/Sources/Core/Inference/TextDecodeEngine.swift`
- If `execution.cache_hints.save_boundary_snapshot` is enabled and the decode completes cleanly, save a boundary snapshot and emit a `snapshot_created` execute event.
- If the decode resumed from a snapshot, emit a `cache_decision` event with the restored snapshot identifier before token streaming begins.

### 3. Add phase-aware worker client routing in the control plane

- Modify `services/control-plane-swift/Sources/WorkerClient/*`
- Modify `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
- Add phase-aware worker client methods for `Prefill` and `Decode`.
- Session-tagged chat requests should use `Prefill -> Decode` when restore or boundary-save recovery is active.
- The control plane should hydrate session graph state when `snapshot_created` events arrive.

### 4. Add request-level recovery metadata to the chat translator

- Modify `services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift`
- Add optional request metadata for:
  - `session_id`
  - `branch_id`
  - `parent_request_id`
  - `restore_snapshot_id`
  - `save_boundary_snapshot`
- Default session-tagged requests to boundary-save enabled so the session graph can accumulate resume points.

### 5. Prove recovery through tests and local integration

- Modify `services/control-plane-swift/Tests/HTTPGatewayTests/*`
- Modify `services/mlx-text-worker-swift/Tests/CoreTests/*`
- Add integration tests under `tests/integration`
- Cover:
  - restore-aware prefill
  - decode snapshot-created events
  - session-tagged request hydration
  - restart-safe restore with a persisted disk cache root

## Verification

```bash
make swift-test
make py-test
make integration-test
swift test --package-path services/control-plane-swift --enable-code-coverage
swift test --package-path services/mlx-text-worker-swift --enable-code-coverage
git diff --check
```

## Acceptance

- The Swift text worker can resume from a saved boundary snapshot through the active `Prefill` path.
- The decode path can save and report new boundary snapshots without direct operator intervention.
- Session-tagged requests can restore recovery state through the control plane instead of only through direct worker RPC calls.
- Integration tests prove restart-safe recovery on the deterministic Swift backend.
