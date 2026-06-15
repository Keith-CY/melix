# Persistent Sessions

## Purpose

Configure and verify Melix remember-me authentication sessions without mixing them into model session graphs or desktop-local UI state.

M9.4 adds a gateway-scoped auth-session workflow:

- `POST /v1/melix/auth/session` creates a typed gateway session from an already valid gateway credential
- `GET /v1/melix/auth/session` inspects the active session via `X-Melix-Session`
- `DELETE /v1/melix/auth/session` revokes the session and records sign-out latency.
  Revocation consumes the token once; repeated or concurrent sign-out attempts for
  the same token return `401 revoked_session`.

Remembered sessions survive process restart until TTL expiry or explicit revocation. Non-remembered sessions remain process-local and disappear on restart.

## Environment Configuration

```bash
export MELIX_GATEWAY_AUTH_MODE=api_keys
export MELIX_GATEWAY_SHARED_ACCESS_ENABLED=true
export MELIX_GATEWAY_API_KEYS_JSON='[
  {"id":"desktop-agent","label":"Desktop Agent","token_hint":"desktop-agent","token":"sk-desktop"}
]'
export MELIX_PERSISTENT_AUTH_SESSION_TTL_SECONDS=3600
```

Optional storage override:

```bash
export MELIX_HOME="${PWD}/.runtime/m9-persistent-sessions"
```

Remembered records are written to:

- `${MELIX_HOME}/state/persistent-auth-sessions.json` when `MELIX_HOME` is set
- `~/.melix/state/persistent-auth-sessions.json` otherwise

The persisted document stores only session metadata and a token hash. It never stores the raw API key or raw session token.

## Manual Verification

### Create A Remembered Session

```bash
curl -sS \
  -H 'content-type: application/json' \
  -H 'x-api-key: sk-desktop' \
  -d '{"remember_me":true}' \
  http://127.0.0.1:${MELIX_HTTP_PORT:-12436}/v1/melix/auth/session
```

Expected response:

- `200`
- `resume.header = "x-melix-session"`
- `resume.token` present
- `session.remember_me = true`

### Create A Companion Pairing Session

```bash
curl -sS \
  -H 'content-type: application/json' \
  -H 'x-api-key: sk-desktop' \
  -d '{"remember_me":true,"scope":"companion_read_only"}' \
  http://127.0.0.1:${MELIX_HTTP_PORT:-12436}/v1/melix/auth/session
```

Expected response:

- `200`
- `session.scope = "companion_read_only"`
- `resume.header = "x-melix-session"`
- `resume.token` present
- `pairing.schema_version = "melix.companion.pairing.v1"`
- `pairing.status_url` points at `/v1/melix/companion/status`
- `pairing.allowed_routes` lists the read-only companion routes and
  self-revocation route
- `pairing.forbidden_capabilities` includes mutating and private-content
  capabilities such as `run_inference`, `mutate_runtime`, and
  `read_private_prompts`

The pairing descriptor is safe to render in a QR/token-management sheet because
it describes how the companion client should use the session. It does not
duplicate the raw token. Keep treating `resume.token` as the only secret value
in the response.

### Desktop Companion Token Controls

The macOS API workspace includes a `Companion Pairing` panel under the
Authentication section. It uses the selected local server session's stored
primary gateway API key to issue a remembered `companion_read_only` session,
then renders the safe pairing descriptor returned by the gateway.

Operator actions:

- `Issue Read-Only Token` calls `POST /v1/melix/auth/session` with
  `remember_me = true` and `scope = companion_read_only`.
- `Copy Pairing Bundle` copies a one-time JSON bundle containing the descriptor
  and the raw companion token for the operator to transfer to a companion
  client.
- `Revoke Token` calls `DELETE /v1/melix/auth/session` with the active
  companion token through `X-Melix-Session`.

The desktop view model keeps the raw companion token only in transient process
memory so the current operator session can copy or revoke it. The token is not
written into operator session state, server-session configuration, logs,
metrics, or the safe descriptor displayed in the panel. Closing the desktop
process drops the transient token reference; create a new companion token if the
current token can no longer be copied or revoked from the panel.

### Desktop Companion Status Refresh

The macOS API workspace also includes a `Companion Status` panel under the
Authentication section. It is a read-only status probe for the active companion
pairing token. The panel calls the gateway `GET /v1/melix/companion/status`
route with the transient companion token and renders only the safe response
fields returned by the gateway.

Operator action:

- `Refresh Status` calls the descriptor `pairing.status_url` with the descriptor
  `pairing.resume_header` and active companion token.

The desktop app does not tail local log files, persist fetched companion status,
or expand the companion session allowlist. Gateway authorization and redaction
remain the source of truth. The displayed log-tail rows must come from the
response `logs.entries` collection and must keep raw log lines, private prompts,
request bodies, artifact URIs, local paths, and raw error text omitted according
to the response `redaction` labels.

### Reuse The Session

```bash
curl -sS \
  -H "X-Melix-Session: ${MELIX_SESSION_TOKEN}" \
  http://127.0.0.1:${MELIX_HTTP_PORT:-12436}/v1/models
```

Expected response:

- `200`
- public model list payload

### Restart Restore Check

After restarting the local stack with the same `MELIX_HOME` and gateway keyring:

```bash
curl -sS \
  -H "X-Melix-Session: ${MELIX_SESSION_TOKEN}" \
  http://127.0.0.1:${MELIX_HTTP_PORT:-12436}/v1/melix/auth/session
```

Expected response:

- `200`
- `session.last_restored_at_unix_ms > 0`

### Sign Out

```bash
curl -sS -X DELETE \
  -H "X-Melix-Session: ${MELIX_SESSION_TOKEN}" \
  http://127.0.0.1:${MELIX_HTTP_PORT:-12436}/v1/melix/auth/session
```

Expected follow-up rejection:

```bash
curl -sS \
  -H "X-Melix-Session: ${MELIX_SESSION_TOKEN}" \
  http://127.0.0.1:${MELIX_HTTP_PORT:-12436}/v1/models
```

- status `401`
- `error.code = "revoked_session"`
- `error.session_state.state = "revoked"`

Repeating the same `DELETE /v1/melix/auth/session` request after a successful
sign-out must also return `401 revoked_session`. Treat this as the expected
single-consumption result, not as an operator-facing success.

### Non-Remembered Session Check

Create an ephemeral session:

```bash
curl -sS \
  -H 'content-type: application/json' \
  -H 'x-api-key: sk-desktop' \
  -d '{"remember_me":false}' \
  http://127.0.0.1:${MELIX_HTTP_PORT:-12436}/v1/melix/auth/session
```

After restart, the same token must fail with:

- status `401`
- `error.code = "missing_session"`
- `error.session_state.state = "missing"`

## Desktop Operator State

The desktop gateway summary now surfaces:

- active auth-session count
- remembered auth-session count
- expired remembered-session count
- retention TTL
- last sign-out latency

This projection comes from control-plane metrics and does not expose raw session tokens.

## Deterministic Smoke

Run the repository-owned smoke command:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python python scripts/m9_persistent_session_smoke.py --json
```

The smoke covers:

- remembered session creation
- restart restore
- sign-out and revoked-session rejection
- non-remembered session invalidation after restart

## Metrics

Persistent sessions and companion desktop controls record these metrics in the
touched scope:

- `persistent_session.active_session_count`
- `persistent_session.remembered_session_count`
- `persistent_session.expired_session_count`
- `persistent_session.restore_success_rate`
- `persistent_session.sign_out_latency_ms`
- `persistent_session.retention_ttl_seconds`
- `companion.status_refresh_ms`
- `companion.status_refresh_failures`
