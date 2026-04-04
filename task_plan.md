# Task Plan

## Goal

Start `M10.1` by introducing an explicit server-session runtime lifecycle and power-state snapshot
model so Melix can project typed `paused` versus `sleeping`, wake-reason, idle-timer, and
auto-sleep metadata without overloading the existing Phase 3 branch/session graph semantics.

## Scope

- extend the control-plane protocol with a dedicated server-session runtime snapshot type
- project the new runtime-session state through control-plane snapshots and `server.state_changed`
  events
- wire the typed runtime-session payload into the native menu bar client state without adding the
  later `M10.2` control commands or `M10.3` banner policy
- add focused Swift coverage for proto decode, snapshot/event projection, and menu bar consumption

## Phases

1. Protocol boundary and task split
   - status: completed
   - evidence:
     - keep Phase 3 `SessionState` and `snapshot.sessions` reserved for branch/session graph state
     - add a separate server-runtime session type for lifecycle and power metadata
     - avoid implementing `pause`, `resume`, `stop`, or `wake` controls in this slice
2. Snapshot and event projection
   - status: completed
   - evidence:
     - extend the snapshot builder and control-plane event payloads with typed runtime-session
       fields
     - keep existing `server_state` backward-compatible while adding richer runtime metadata
3. Menu bar state and focused tests
   - status: completed
   - evidence:
     - consume the new runtime-session payload in `RuntimeViewModel` and related UI state models
     - add focused control-plane and menu bar tests for snapshot/event decoding and lifecycle-state
       projection
4. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - run `make proto`, focused Swift suites, and `make swift-test`
     - record changed-line coverage at or above `95%`, update `progress.md`, and mark `M10.1`
       completed only after evidence is recorded

## Acceptance

- protocol changes introduce a typed server-session runtime lifecycle model without mutating the
  existing branch/session graph contract
- control-plane snapshots and `server.state_changed` events expose explicit lifecycle and power
  metadata that clients can consume without local inference
- the native menu bar client can decode and store the new runtime-session payload without banner or
  control-policy placeholders
- focused Swift verification and changed-line coverage evidence cover the touched protocol,
  snapshot, and UI-consumption paths

## Risks

- reusing the existing Phase 3 `SessionState` for power lifecycle would corrupt branch recovery and
  cache/session semantics that already depend on that contract
- adding real pause/resume/stop controls in this slice would bleed into `M10.2` and destabilize
  the first typed protocol step
- teaching the menu bar to infer lifecycle locally instead of consuming the new runtime-session
  payload would reintroduce exactly the ambiguity `M10.1` is meant to remove

## Outcome

- m10_1_server_session_runtime_snapshot_foundation_completed
