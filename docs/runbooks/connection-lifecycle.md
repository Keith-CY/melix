# Connection Lifecycle

## Purpose

Harden Melix chat streaming against transient client disconnects without silently aborting in-flight work or leaking request state.

`M9.6` adds a repository-owned connection lifecycle contract for the chat streaming path:

- keepalive comments are emitted on a policy-driven cadence
- a disconnected stream enters a bounded resume grace window instead of aborting immediately
- a resumed stream preserves the original request identity and reattaches to the in-flight execution
- an expired resume window fails with a typed `request_not_resumable` error instead of a silent timeout

The lifecycle contract applies to the control-plane chat execution hub and the HTTP chat streaming surface. It does not change worker-side execution semantics or model outputs.

## Environment Configuration

The lifecycle policy is loaded from process environment with repository-owned defaults.

```bash
export MELIX_CONNECTION_KEEPALIVE_INTERVAL_SECONDS=15
export MELIX_CONNECTION_DISCONNECT_GRACE_SECONDS=5
export MELIX_CONNECTION_RETRY_BACKOFF_SECONDS=0.5
export MELIX_CONNECTION_RETRY_LIMIT=0
export MELIX_CONNECTION_RESUME_BUFFER_LIMIT=512
```

Semantics:

- `MELIX_CONNECTION_KEEPALIVE_INTERVAL_SECONDS`
  - interval between SSE keepalive comments
  - set to `0` to disable keepalive emission
- `MELIX_CONNECTION_DISCONNECT_GRACE_SECONDS`
  - how long a disconnected stream remains resume-eligible before the coordinator expires it
- `MELIX_CONNECTION_RETRY_BACKOFF_SECONDS`
  - backoff surfaced in lifecycle policy for retry-aware callers
- `MELIX_CONNECTION_RETRY_LIMIT`
  - maximum retry attempts recorded in the lifecycle policy
- `MELIX_CONNECTION_RESUME_BUFFER_LIMIT`
  - how many stream events remain available for replay when a consumer reattaches

For local validation the repository tests use shorter values, for example:

```bash
export MELIX_CONNECTION_KEEPALIVE_INTERVAL_SECONDS=0.005
export MELIX_CONNECTION_DISCONNECT_GRACE_SECONDS=5
export MELIX_CONNECTION_RETRY_BACKOFF_SECONDS=0.01
export MELIX_CONNECTION_RETRY_LIMIT=1
export MELIX_CONNECTION_RESUME_BUFFER_LIMIT=256
```

## Resume Contract

The HTTP chat stream stays resumable only while the disconnect grace window is still open.

Resume request shape:

```json
{
  "model": "melix-dev-text",
  "stream": true,
  "resume_request_id": "chatcmpl-...",
  "messages": [
    {"role": "user", "content": "resume the active stream"}
  ]
}
```

Expected behavior:

- a successful resume returns `200`
- the resumed stream keeps the original `request_id`
- replayed output terminates with `data: [DONE]`
- an expired resume returns `409`
- the typed error payload uses `error.code = "request_not_resumable"`

## Manual Verification

### Observe Keepalive Comments

Start the local stack, then stream a long enough prompt:

```bash
curl -N -sS \
  -H 'content-type: application/json' \
  -d '{
    "model":"melix-dev-text",
    "stream":true,
    "messages":[{"role":"user","content":"emit enough tokens to observe keepalive comments"}]
  }' \
  "http://127.0.0.1:${MELIX_HTTP_PORT:-11434}/v1/chat/completions"
```

Expected stream shape:

- at least one line starting with `: keepalive `
- normal `data: ...` event frames
- a terminal `data: [DONE]`

### Resume A Disconnected Stream

1. Start a streaming request and capture the first non-empty `request_id`.
2. Close the client connection without cancelling the request.
3. Reconnect within the configured disconnect grace:

```bash
curl -N -sS \
  -H 'content-type: application/json' \
  -d '{
    "model":"melix-dev-text",
    "stream":true,
    "resume_request_id":"chatcmpl-REPLACE-ME",
    "messages":[{"role":"user","content":"resume the active stream"}]
  }' \
  "http://127.0.0.1:${MELIX_HTTP_PORT:-11434}/v1/chat/completions"
```

Expected outcome:

- status `200`
- resumed events retain the original `request_id`
- the resumed body does not include `stream_disconnect_timeout`
- the stream completes with `data: [DONE]`

### Verify Terminal Expiry

Wait until the disconnect grace window has expired, then retry the same `resume_request_id`.

Expected outcome:

- status `409`
- `error.code = "request_not_resumable"`

## Deterministic Smoke

Run the repository-owned smoke command:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python python scripts/m9_connection_smoke.py --json
```

The smoke covers:

- keepalive emission
- successful resume within disconnect grace
- terminal expiry after disconnect grace elapses

## Metrics

`M9.6` records these metrics in the touched scope:

- `http.stream_disconnect_count`
- `disconnect.keepalive_gap_ms`
- `disconnect.recovery_latency_ms`
- `disconnect.resume_success_rate`
- `disconnect.terminal_failure_count`

Interpretation:

- `disconnect.keepalive_gap_ms`
  - most recent observed gap between keepalive emissions
- `disconnect.recovery_latency_ms`
  - measured latency between detach and successful consumer reattachment
- `disconnect.resume_success_rate`
  - `100` after a successful recovery, `0` after an expired terminal disconnect
- `disconnect.terminal_failure_count`
  - increments when a disconnected request ages out of the resume window

## Troubleshooting

- If resume returns `request_not_resumable` too early, verify `MELIX_CONNECTION_DISCONNECT_GRACE_SECONDS` in the control-plane environment and confirm the client is reattaching before the grace timer expires.
- If resumed streams still surface `stream_disconnect_timeout`, inspect the coordinator lifecycle path and confirm the disconnect grace task is cancelled when a consumer reattaches.
- If keepalive metrics are missing, confirm keepalives are enabled and that the client keeps the stream open long enough to observe at least one keepalive interval.
- If a resumed stream changes `request_id`, inspect the control-plane resume path and confirm it is reattaching to an existing execution instead of creating a new request.
