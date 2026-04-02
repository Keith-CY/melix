# M9.4 Server-Session API Key Persistence And Melix Home Design

## Context

The existing `M9.4` implementation plan is framed around persistent auth sessions and remember-me behavior. That framing no longer matches the clarified product direction for Melix.

Confirmed product constraints:

- Melix is local-first and should not introduce account-style sign-in or remembered remote auth sessions for this slice.
- A generated API key is sufficient for local OpenAI-compatible access.
- API-key material may be stored in repository-owned JSON rather than Keychain.
- App and future CLI surfaces should share one product-owned filesystem home under `~/.melix`.
- The product is pre-release, so no compatibility layer or automatic migration from `~/Library/Application Support/Melix` is required.

Confirmed architectural constraints from the current codebase:

- the Swift control plane starts one real HTTP listener per process
- the HTTP gateway uses one effective `GatewayAccessPolicy` at a time
- the desktop `Server Session` currently projects gateway auth state rather than owning an already-isolated per-session listener instance
- productization scripts and docs still point several runtime artifacts at `~/Library/Application Support/Melix`

This design replaces remember-me semantics with server-session-owned API-key persistence and a unified `~/.melix` layout.

## Goal

Make `Server Session` the owner of its primary API key, persist local operator recovery state and secret material under `~/.melix`, and ensure the currently active Melix gateway applies the selected server session's primary key as real runtime auth rather than UI-only state.

## Non-Goals

This design does not cover:

- account login, logout, refresh tokens, OAuth, or remote identity providers
- generic persistent auth sessions for arbitrary external HTTP clients
- Keychain or notarization-dependent secret storage
- true multi-listener or multi-gateway runtime support in this slice
- Chat-owned API keys or chat-specific auth state
- backward compatibility or migration from `~/Library/Application Support/Melix`

## Recommended Approach

Persist one primary API key per `Server Session`, keep non-secret restore state separate from secret values, and let the currently active server session project its persisted key into the control plane through a typed runtime mutation.

Why this approach:

- it keeps `Server Session` as the product object that owns listener-oriented auth intent
- it avoids a fake UI that edits per-session keys while the runtime still enforces one global gateway policy
- it preserves a clean path to future true multi-listener support because persistence ownership stays attached to `Server Session`
- it lets App and future CLI share one product-owned filesystem layout without introducing App-only state

## Alternatives Considered

### 1. Global Gateway Key Editor Only

Treat the `Server Session` API-key controls as an editor for one global runtime key with no per-session persistence.

Pros:

- lowest implementation cost
- matches today's single-listener runtime exactly

Cons:

- makes `Server Session` a misleading editing surface
- creates semantic debt for future real per-session listeners
- couples operator UI too tightly to current bootstrap limitations

### 2. Recommended: Session-Owned Keys With Single-Gateway Projection

Persist primary API keys by `serverSessionID`, but only one running or operator-applied server session projects its key into the active gateway at a time.

Pros:

- keeps product semantics aligned with the `Server Session` model
- preserves truthfulness in the current single-gateway runtime
- provides a clean upgrade path to true multi-listener support later

Cons:

- requires both local persistence work and a typed control-plane mutation
- requires explicit restore logic instead of relying only on bootstrap environment variables

### 3. Full Multi-Listener Redesign Now

Expand the control plane so each `Server Session` owns its own listener and gateway policy immediately.

Pros:

- most architecturally pure outcome
- fully matches the long-term server-session model

Cons:

- much larger scope than `M9.4`
- expands runtime, protocol, lifecycle, and diagnostics work well beyond the current need

## Architecture

### 1. Ownership And Product Semantics

`Server Session` owns listener-oriented auth intent.

For this slice, that means:

- a server session may have zero or one persisted primary API key
- the primary API key belongs to the server session, not to a chat session
- Chat continues to bind to a server session and inherits its effective access behavior indirectly
- the API page and export surfaces continue to explain access in terms of the selected server session

There is no sign-in surface in this design. The operator either has no API key configured for a server session or that server session has a primary key stored locally.

### 2. Runtime Authority Boundary

The control plane remains the authority for the effective in-memory `GatewayAccessPolicy`. Local persistence under `~/.melix` is operator-owned product state shared by App and future CLI surfaces.

The runtime model for this slice is:

- only one HTTP listener is active per Melix runtime process
- only one effective gateway access policy is active at a time
- the active policy is sourced from the active server session bound to the single running listener
- the control plane exposes a typed command that applies gateway access from a server-session-scoped payload
- control-plane snapshots continue to expose only auth mode, key count, and non-secret hints

This keeps the desktop shell from becoming a second control plane while still allowing local operator tooling to persist and restore state.

For this slice, an active server session means the locally selected or restored server session that is currently bound to the runtime's single effective listener. If a server session has a persisted primary key but is not yet active, its key remains stored but is not enforced by the gateway until that server session becomes active.

### 3. Persistence Layout Under `~/.melix`

Melix should introduce `MELIX_HOME`, defaulting to `$HOME/.melix`.

Derived paths:

- `~/.melix/install/install-manifest.json`
- `~/.melix/env/melix-product-env.sh`
- `~/.melix/runtime/`
- `~/.melix/logs/`
- `~/.melix/state/operator-session.json`
- `~/.melix/secrets/server-session-api-keys.json`

Directory responsibilities:

- `install/` stores local installation metadata only
- `env/` stores shell export fragments used by App and CLI launch paths
- `runtime/` stores sockets, pid-style runtime artifacts, and metrics snapshots
- `logs/` stores control-plane and worker stdout/stderr logs
- `state/` stores non-secret local operator restore state
- `secrets/` stores secret-bearing API-key data

No new product-owned local-install or app-bundle artifact should continue writing to `~/Library/Application Support/Melix`.

### 4. File Formats

`operator-session.json` stores non-secret operator recovery state only. It may include:

- selected top-level surface
- selected `serverSessionID`
- persisted server-session drafts or local configuration snapshots
- chat-to-server-session binding metadata needed for local UI recovery
- last-opened object identity and window-local restore state

It must not store plaintext API keys.

`server-session-api-keys.json` stores only the minimum secret-bearing server-session key records required for local reuse. Each record should include:

- `server_session_id`
- `key_id`
- `primary_key`
- `updated_at`

Suggested top-level shape:

```json
{
  "schema_version": 1,
  "sessions": [
    {
      "server_session_id": "server-123",
      "key_id": "primary",
      "primary_key": "melix_sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "updated_at": "2026-04-02T13:45:00Z"
    }
  ]
}
```

`primary_key` is the only plaintext secret field in this document.

### 5. API-Key Format And Hinting

Generated primary keys should be opaque, high-entropy, and product-identifiable. The recommended format is:

- prefix: `melix_sk_`
- random payload: at least `32` bytes of cryptographically secure randomness encoded in URL-safe text

The displayed token hint must not expose the full secret. Snapshot-visible hinting should be derived from stable metadata or a redacted form, for example `primary` or a masked short form. Plaintext values are read only from the local secrets store when the operator explicitly reveals or copies them.

### 6. Operator Interaction Model

The `Server Session` API-key editor behaves as follows:

- default state is masked
- an eye icon inside the field toggles reveal and hide for the current plaintext value
- a copy icon inside the field copies the plaintext primary key
- a refresh icon outside the field generates and replaces the primary key

Generate or refresh semantics:

1. create a new secure API key
2. set the current server session's auth mode to `API Keys`
3. persist the new primary key in `~/.melix/secrets/server-session-api-keys.json`
4. if the current server session is active, apply the effective gateway policy to the control plane immediately
5. refresh the operator snapshot so the selected server session reflects the new auth mode and non-secret hint

There is no remember-me checkbox, no sign-in flow, and no sign-out action in this slice.

### 7. Startup And Restore Flow

Restore remains local and deterministic:

1. App or CLI resolves `MELIX_HOME`, defaulting to `~/.melix`.
2. It loads `operator-session.json` and `server-session-api-keys.json` if present.
3. It restores local operator selection and server-session metadata from non-secret state.
4. When the runtime starts or reconnects, the operator surface applies the active server session's primary key to the control plane through a typed command.
5. The control plane updates the in-memory gateway policy and emits a snapshot that exposes only redacted access metadata.

Missing files are treated as empty state. Restore must not fail hard simply because persisted state has not been created yet.

### 8. Filesystem And Permission Rules

Permissions should be explicit:

- `~/.melix`, `runtime/`, `logs/`, `state/`, and `secrets/` should be created with `0700`
- `operator-session.json` and `server-session-api-keys.json` should be written with `0600`
- writes should use atomic replace semantics to avoid partial-file corruption

Failure handling:

- missing file: treat as unconfigured empty state
- malformed JSON: isolate the error, surface a recoverable operator message, and do not crash the app
- secrets-store write failure: keep the previous in-memory value unchanged and report a persistence error explicitly
- runtime apply failure: keep the UI from claiming success until the control plane acknowledges the new effective policy

### 9. Productization And Path Unification

Productization code should stop exporting `MELIX_APP_SUPPORT_DIR` as the primary home variable and instead export `MELIX_HOME`.

Required changes for a later implementation plan:

- local install artifacts write into `~/.melix/install`, `~/.melix/env`, `~/.melix/runtime`, and `~/.melix/logs`
- the portable app launcher derives runtime and log paths from `MELIX_HOME`
- README and runbooks describe `~/.melix` as the only supported local product home
- future CLI commands read and write the same state and secret files as the App

This design intentionally avoids compatibility shims because the product is not yet released.

## Data Flow

### Generate Or Refresh Primary Key

1. The operator selects a server session in the desktop shell.
2. The operator presses the refresh icon in the API-key control.
3. The operator layer generates a secure new key and persists it to `server-session-api-keys.json`.
4. If that server session is already active, the operator layer issues a typed control-plane command to apply `auth_mode = api_keys` and the new primary key for the selected server session.
5. The control plane rebuilds its effective `GatewayAccessPolicy`.
6. The gateway starts accepting the new key for OpenAI-compatible requests.
7. The updated snapshot projects only redacted auth metadata back to the UI.

If the server session is not yet active, Melix persists the key and applies it later when that server session becomes the active runtime session.

### Local Restore After Restart

1. Melix loads `operator-session.json` and restores the selected server session.
2. Melix loads the selected server session's primary key from `server-session-api-keys.json`.
3. After runtime connection, Melix applies that server session's effective gateway access policy to the control plane.
4. The UI renders the server session with masked local secret state and snapshot-derived runtime status.

## Error Handling

The design must fail explicitly on:

- missing or unreadable `MELIX_HOME` subdirectories
- malformed operator-session or secrets JSON
- inability to generate secure random key material
- control-plane rejection of the apply-gateway-access mutation
- copy or reveal attempts when no primary key exists for the selected server session

Error reporting principles:

- operator-facing errors should describe whether failure happened during generation, persistence, restore, or runtime apply
- plaintext keys must never appear in error messages, logs, metrics, or snapshots
- local file corruption must remain recoverable without requiring repository edits

## Performance Probes And Success Metrics

This slice should define the following measurements before implementation:

- `operator.session_restore_ms`
- `operator.session_persist_write_ms`
- `gateway.api_key_apply_ms`
- `gateway.api_key_persist_failures`

Additional correctness counters may include:

- `gateway.api_key_generate_count`
- `gateway.api_key_reveal_count`
- `gateway.api_key_copy_count`

## Testing Strategy

### Control Plane

- typed tests for runtime application of a server-session primary key
- snapshot tests proving only key hints are exposed and plaintext never leaks
- failure tests for rejected or malformed gateway-access apply commands

### Desktop Shell

- view-model tests for masked-by-default behavior
- reveal and hide tests for the eye control
- copy tests for primary-key availability and empty-state handling
- generate or refresh tests proving auth mode flips to `API Keys` and the runtime apply path is invoked

### Local Persistence

- tests for `operator-session.json` read, write, empty-state, and corruption recovery
- tests for `server-session-api-keys.json` read, write, replacement, and permission handling
- tests that no plaintext key is derived from control-plane snapshot data alone

### Productization

- tests that local-install assets now resolve under `~/.melix`
- tests that app-bundle launcher exports `MELIX_HOME` and derives runtime and log paths from it

### Integration And Smoke

- end-to-end smoke proving a generated primary key becomes immediately valid for `/v1/models`
- rejection smoke proving requests without the configured key are denied when API-key mode is active
- restore smoke proving a restarted local operator session re-applies the selected server session's primary key deterministically

## Acceptance

This design is satisfied when:

- `Server Session` is the persisted owner of the local primary API key
- the active runtime gateway policy is updated through a typed control-plane mutation rather than UI-only local state
- App and future CLI use `~/.melix` as the shared product home
- no new productization or local-install path depends on `~/Library/Application Support/Melix`
- secrets remain in local JSON only and never appear in snapshots or exported examples
- operator restore remains local, deterministic, and recoverable without account-style auth concepts

## Verification Notes

- Automated coverage for this change: `N/A` because this commit records a design document only and does not modify executable paths.
- Changed-scope metrics report: `N/A` because this commit records the design-time probes and success metrics rather than implementation measurements.
