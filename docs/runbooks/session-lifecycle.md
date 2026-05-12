# Session Lifecycle

`M10` closes the Melix session-lifecycle surface with explicit runtime-session lifecycle state,
idle-power policy, desktop visibility, and reproducible smoke evidence.

This runbook covers repository-local diagnosis and recovery for paused, sleeping, stopped, and
failed server sessions.

## Scope

- control-plane-owned runtime-session lifecycle state
- idle policy and auto-sleep thresholds
- wake and restart recovery
- repository-owned lifecycle smoke evidence

## Prerequisites

- a local Melix worker environment with `MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH` and
  `MELIX_WORKER_SOCKET_PATH` exported for the target runtime
- an optional `MELIX_CONTROL_PLANE_METRICS_PATH` if the operator wants the lifecycle smoke to
  persist machine-readable metrics to a known file
- the repository root exported as `MELIX_REPO_ROOT` when running the smoke executable outside the
  default checkout shell

## Inspect Current Lifecycle State

Use the shared server snapshot surface to inspect runtime-session lifecycle, power state, wake
reason, and idle policy:

```bash
swift run melix server snapshot --json
```

Look for:

- `runtime_sessions[].lifecycle_state`
- `runtime_sessions[].power_state`
- `runtime_sessions[].wake_reason`
- `runtime_sessions[].idle_timer_seconds`
- `runtime_sessions[].auto_sleep_enabled`
- `runtime_sessions[].light_sleep_after_seconds`
- `runtime_sessions[].deep_sleep_after_seconds`

## Lifecycle Smoke

Run the repository-owned lifecycle smoke harness from the same shell that already exports the worker
socket paths:

```bash
MELIX_CONTROL_PLANE_METRICS_PATH=/tmp/melix-session-lifecycle-smoke.json \
swift run melix-session-lifecycle-smoke --json
```

The smoke payload reports:

- `lifecycle.pause_ack_ms`
- `lifecycle.idle_to_light_sleep_ms`
- `lifecycle.wake_to_ready_ms`
- `lifecycle.restart_recovery_ms`
- `control_plane.server_start_ms`
- `control_plane.server_pause_ms`
- `control_plane.server_resume_ms`
- `control_plane.server_wake_ms`
- `control_plane.server_stop_ms`
- `control_plane.server_idle_policy_ms`

The smoke scenarios also capture:

- paused-session chat rejection
- idle-policy-driven light sleep
- request-activity wake back to `ready`
- stop and start recovery plus post-restart chat success

## Recovery Guidance

### Paused

- Inspect the server snapshot and confirm `lifecycle_state == "paused"`.
- Resume the session:

```bash
swift run melix server resume --json
```

- If chat still fails after resume, inspect the latest lifecycle smoke output and confirm
  `lifecycle.wake_to_ready_ms` or `control_plane.server_resume_ms` were recorded.

### Sleeping

- Inspect the server snapshot and confirm `lifecycle_state == "sleeping"`.
- Wake explicitly:

```bash
swift run melix server wake --json
```

- A normal request path should also wake the session on demand. If a request wakes the session but
  the operator still sees stale UI state, refresh the desktop snapshot before diagnosing a deeper
  runtime fault.

### Stopped

- Inspect the server snapshot and confirm `lifecycle_state == "stopped"`.
- Restart the serving session:

```bash
swift run melix server start --json
```

- To create or rebind a titled local server session and start it in one command, pass the session
  title plus the model and listener options:

```bash
swift run melix server start "Gemma 31B" \
  --model mlx-community/gemma-4-31b-it-4bit \
  --port 12434 \
  --json
```

- The positional value is the session title. New sessions still receive generated identifiers such as
  `server-session-1`; later shortcut starts reuse an existing session when its identifier or title
  matches the supplied value.

- If the restart path fails with a `conflict`, wait for in-flight requests to finish and retry.
  The lifecycle smoke harness already applies a short quiescence retry before recording
  `lifecycle.restart_recovery_ms`.

### Failed

- Inspect the desktop banner, the server snapshot, and the control-plane metrics export.
- If the failure is limited to a transient client disconnect, use the connection-specific guidance
  in [`connection-lifecycle.md`](./connection-lifecycle.md).
- If the runtime session remains in `error`, restart the session and rerun the lifecycle smoke to
  capture a fresh machine-readable report before changing lower-level runtime settings.

## Distinguishing Lifecycle Faults From Connection Churn

- Use `server snapshot` and the lifecycle smoke first for session-state faults.
- Use [`connection-lifecycle.md`](./connection-lifecycle.md) for stream disconnects, resume grace,
  keepalive gaps, and client reconnect timing.
- Do not treat a successful reconnect as proof that a paused or sleeping server session recovered;
  lifecycle and connection evidence are separate.
