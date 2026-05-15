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

When the same keyring is configured with `MELIX_GATEWAY_SHARED_ACCESS_ENABLED=false`, Melix keeps local trust active, rejects explicit shared-auth headers, and advertises the key hints as `Configured, Disabled` in the desktop state.

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
