# Task Plan

## Goal

Close `M10.3` by surfacing the control-plane-owned server lifecycle and power-state truth across the
desktop shell, chat workspace, and operator controls so loading, paused, sleeping, stopped, and
failed sessions are obvious and actionable from Window UI.

## Scope

- project runtime-session lifecycle, power-state, wake-reason, and idle-policy metadata into the
  desktop shell banner model and server workspace summary surfaces
- add session-scoped operator controls for pause, resume, wake, stop, and idle-policy updates using
  the new control-plane client methods instead of local UI inference
- make chat-facing and server-facing surfaces distinguish loading, paused, sleeping, stopped, and
  failed sessions with deterministic control enablement rules
- add focused menu bar and control-plane Swift coverage for banner derivation, control gating,
  reconnect hydration, and typed state transitions

## Measurement Points

- desktop banner and server-workspace state must be fully derivable from `ServerSessionRuntimeState`
  payloads without ad-hoc local lifecycle heuristics
- operator control enablement must stay consistent across initial hydration and later
  `server.state_changed` events for the same server session
- banner and control changes should emit measurable desktop metrics so later `M10.4` evidence can
  trace server-session visibility and interaction latency

## Phases

1. Desktop state projection
   - status: pending
   - evidence:
     - inspect the existing runtime-session projection in `RuntimeViewModel`,
       `DesktopFoundationState`, and the dashboard shell to locate where server lifecycle state is
       still summarized only as coarse server status
     - define the banner and workspace state needed to distinguish loading, paused, sleeping,
       stopped, and failed sessions from control-plane truth
2. Operator controls and chat-facing affordances
   - status: pending
   - evidence:
     - wire the new session-scoped lifecycle and idle-policy client methods into the desktop shell
       and server workspace controls
     - ensure control enablement and banner copy remain aligned with session lifecycle truth during
       hydration, reconnect, and explicit operator actions
3. Verification and milestone bookkeeping
   - status: pending
   - evidence:
     - run the relevant focused menu bar and control-plane Swift suites plus repository-default
       verification for the touched scope
     - record changed-line coverage at or above `95%`, update `progress.md`, and mark `M10.3`
       completed only after evidence is captured

## Acceptance

- desktop surfaces expose accurate lifecycle banners and server-workspace summaries for all typed
  runtime-session states
- operator controls remain valid, disabled, or hidden according to authoritative session lifecycle
  and idle-policy truth
- reconnect hydration and follow-up `server.state_changed` events preserve the same banner and
  control state without local re-interpretation

## Risks

- re-deriving lifecycle state locally in the desktop shell would drift from the control plane and
  break later API and evidence slices
- exposing controls without typed gating could let operators trigger invalid transitions and muddy
  the `M10.4` evidence path
- banner logic that only updates on full snapshots could miss reconnect or event-stream transitions
  and leave the desktop shell stale

## Outcome

- m10_3_desktop_status_banners_and_operator_surfaces_in_progress
