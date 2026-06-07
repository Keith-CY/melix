# Shared Access

## Purpose

Configure Melix to safely serve more than one local client by switching from implicit local trust to an explicit gateway access policy.

M9.3 supports:

- local-trust mode with no auth header
- a single bearer-token policy
- a shared API-key policy with multiple stable key IDs and operator-safe hints

Melix keeps raw secrets in the control-plane process only. Snapshot and desktop surfaces project safe key hints and effective access state without copying secret values into app state.

## Environment Configuration

### Local Trust

Unset the gateway variables or set:

```bash
export MELIX_GATEWAY_AUTH_MODE=none
```

This keeps local trusted access enabled and does not require auth headers.

### Single Bearer Token

```bash
export MELIX_GATEWAY_AUTH_MODE=bearer_token
export MELIX_GATEWAY_BEARER_TOKEN='sk-local-bearer'
export MELIX_GATEWAY_BEARER_TOKEN_ID='primary-bearer'
export MELIX_GATEWAY_BEARER_TOKEN_HINT='primary-bearer'
```

Clients must send:

```text
Authorization: Bearer sk-local-bearer
```

### Shared API Keys

```bash
export MELIX_GATEWAY_AUTH_MODE=api_keys
export MELIX_GATEWAY_SHARED_ACCESS_ENABLED=true
export MELIX_GATEWAY_API_KEYS_JSON='[
  {"id":"desktop-agent","label":"Desktop Agent","token_hint":"desktop-agent","token":"sk-desktop"},
  {"id":"codex","label":"Codex","token_hint":"codex","token":"sk-codex"}
]'
```

When shared access is enabled, Melix accepts either:

```text
x-api-key: sk-codex
```

or:

```text
Authorization: Bearer sk-codex
```

Both header forms resolve to the configured key ID. Rate limiting uses that
accepted credential identity, not the literal header name, so the same key
shares one quota across OpenAI-compatible clients that prefer bearer tokens and
Melix clients that prefer `x-api-key`.

When the same keyring is configured with `MELIX_GATEWAY_SHARED_ACCESS_ENABLED=false`, Melix keeps local trust active, rejects explicit shared-auth headers, and advertises the key hints as `Configured, Disabled` in the desktop state.

### Rate Limit

The active gateway listener enforces `rate_limit_per_minute` from the gateway
configuration summary. Operators can set the default with:

```bash
export MELIX_GATEWAY_RATE_LIMIT_PER_MINUTE=120
```

Rejected requests return `429 rate_limited` with `retry-after`,
`x-ratelimit-limit`, and `x-ratelimit-remaining` headers. The JSON body includes
only the normalized credential identity, limit, and retry delay; raw tokens are
not echoed.

## Local Server Host and Browser Origin Policy

The OpenAI-compatible local gateway validates `Host` and browser `Origin`
headers before authentication, rate limiting, request decoding, or route
execution.

By default, Melix accepts loopback hosts only:

- `127.0.0.1`
- `[::1]`
- `::1`
- `localhost`

Requests with a different `Host` return `403 host_not_allowed`. Raw HTTP/1.1
requests that omit `Host` are rejected by the gateway parser with
`400 missing_host_header` before route handling. Same-host server-to-server
requests that do not send an `Origin` header remain accepted subject to the
active gateway auth policy.

Browser CORS is default-denied. Requests with an `Origin` header return
`403 origin_not_allowed` unless the origin is explicitly allowlisted. Melix does
not emit wildcard `Access-Control-Allow-Origin`.

For a trusted browser client, allow the browser host and origin explicitly:

```bash
export MELIX_ALLOWED_HOSTS='127.0.0.1,localhost'
export MELIX_ALLOWED_ORIGINS='http://localhost:5173'
```

Allowed origin configuration is normalized to scheme, host, and optional port;
paths, queries, and fragments are ignored because browser `Origin` headers do
not include them. Runtime `Origin` checks are exact matches against those
normalized origins. When an origin is allowed, responses echo only that origin
and add `Vary: Origin`. Browser preflight requests use `OPTIONS` and are
admitted after Host/Origin validation, before API-key authentication, so browser
clients can preflight authenticated routes without exposing credentials in the
preflight request.

The authenticated diagnostics endpoint reports the effective policy under
`local_server_security`:

```bash
curl -sS \
  -H 'x-api-key: sk-codex' \
  http://127.0.0.1:${MELIX_HTTP_PORT:-12436}/v1/melix/health
```

## Operator Checks

### Models Endpoint

Shared-enabled example:

```bash
curl -sS \
  -H 'x-api-key: sk-codex' \
  http://127.0.0.1:${MELIX_HTTP_PORT:-12436}/v1/models
```

Bearer example:

```bash
curl -sS \
  -H 'Authorization: Bearer sk-codex' \
  http://127.0.0.1:${MELIX_HTTP_PORT:-12436}/v1/models
```

Expected failure probes:

- no header in shared-enabled mode returns `401` with `missing_api_key`
- unknown shared key returns `401` with `invalid_api_key`
- explicit shared headers in configured-but-disabled mode return `403` with `shared_access_disabled`

### Route Parity

The same shared-access policy applies to every operator-facing route except public liveness
`/health`, including text generation, embeddings, rerank, audio transcription, audio speech,
image generation/editing, authenticated health diagnostics at `/v1/melix/health`, discovery,
cache stats, auth session creation, and unknown routes. Missing credentials in shared-enabled
mode must return `401 missing_api_key` before request body decoding or worker dispatch. Session
inspect and revoke routes require `X-Melix-Session`; missing session credentials return
`401 missing_session` and do not fall through to the route handler.

### Desktop State

After the menu bar app hydrates from handshake:

- `Server` and `API` surfaces show the effective access mode from the control-plane snapshot
- shared-enabled mode surfaces safe key hints and the shared key count
- configured-but-disabled mode keeps exports in local-trust form while still surfacing prepared key hints

## Deterministic Smoke

Run the repository-owned smoke command:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python python scripts/m9_shared_access_smoke.py --json
```

The smoke covers two scenarios:

- shared access enabled with multi-key acceptance, missing-header rejection, and unknown-key rejection
- shared access configured but disabled with local-trust compatibility and explicit shared-header rejection

## Metrics

M9.3 records these metrics in the touched scope:

- `gateway.auth_validation_failures`
- `gateway.accepted_api_key_count`
- `shared_access.accepted_client_count`
- `shared_access.rejected_request_count`
- `gateway.rate_limit_per_minute`
- `gateway.rate_limit_remaining`
- `gateway.rate_limit_last_admission`
- `gateway.rate_limited_request_count`

Supporting snapshot and bootstrap probes also expose:

- `gateway.auth_mode_code`
- `shared_access.enabled`
- `shared_access.ready`

These values are projected into the control-plane snapshot and desktop operator state so backend truth, smoke evidence, and menu bar rendering stay aligned.

Issue 77 also records:

- `route_auth_policy`
- `endpoint_type_validation_result`
- `endpoint_type_validation_rejection_count`

`route_auth_policy` is emitted for non-health requests after the gateway selects the effective
access policy. `endpoint_type_validation_result = 0` with an incremented rejection count means the
request selected a model that belongs to a different endpoint family; the JSON error body includes
the requested endpoint, model endpoint family, and suggested retry endpoint.
