# M9.4 Persistent Session Foundation Transaction

**Goal:** Land the first executable `M9.4` slice by adding gateway-scoped auth sessions with remember-me persistence, bootstrap restore, deterministic expiry pruning, operator-visible snapshot metrics, and repository-owned smoke coverage.

**Scope Boundary:** This transaction introduces a minimal HTTP auth-session workflow on top of the existing `M9.3` shared-access policy. It does not add a new control-plane command family, does not expand protobuf schemas, and does not solve the broader connection lifecycle work reserved for `M9.6`.

## Design Choice

- Reuse the existing typed `GatewayAccessPolicy` as the credential authority.
- Add a dedicated `PersistentAuthSessionStore` in the control-plane Swift workspace.
- Keep persistent session truth in the gateway and bootstrap layer.
- Project operator-visible remembered-session state through existing snapshot metrics and `gateway_access`, rather than introducing a new protocol message in this slice.

## Session Contract

- `POST /v1/melix/auth/session`
  - Requires an already valid gateway credential (`Authorization: Bearer` or `x-api-key`).
  - Accepts `{ "remember_me": bool }`.
  - Returns a one-time session token plus typed session metadata.
- `GET /v1/melix/auth/session`
  - Requires `X-Melix-Session`.
  - Returns typed session metadata for the active gateway session.
- `DELETE /v1/melix/auth/session`
  - Requires `X-Melix-Session`.
  - Revokes the session and returns sign-out metadata.

## Persistence Rules

- Remembered sessions are stored under `MELIX_HOME/state/persistent-auth-sessions.json` when `MELIX_HOME` is set; otherwise use `~/.melix/state/persistent-auth-sessions.json`.
- Store only:
  - session ID
  - key ID
  - remember-me flag
  - token hash
  - created timestamp
  - expiry timestamp
  - revoked timestamp
  - last restored timestamp
- Never persist the raw gateway credential or raw session token.
- Non-remembered sessions remain process-local and disappear on restart.

## Metrics Projection

- `persistent_session.restore_success_rate`
- `persistent_session.expired_session_count`
- `persistent_session.sign_out_latency_ms`
- `persistent_session.active_session_count`
- `persistent_session.remembered_session_count`
- `persistent_session.retention_ttl_seconds`

## Execution Slices

1. Add the persistent auth-session store, bootstrap restore path, and control-plane metrics projection.
2. Add gateway session create/inspect/sign-out routes and session-aware authorization failures.
3. Extend the menu bar server-session projection and gateway-access panel with remembered-session counts and retention status.
4. Add deterministic integration and smoke coverage, collect changed-line coverage, and commit the slice.

## Verification

- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'PersistentAuthSessionStoreTests|OpenAIHandlerTests|ControlPlaneServiceTests'`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'PersistentAuthSessionStoreTests|OpenAIHandlerTests|ControlPlaneServiceTests'`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --scratch-path "$(pwd)/.build/menubar-scratch" --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --scratch-path "$(pwd)/.build/menubar-coverage" --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest tests/integration/test_persistent_sessions.py -q`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest tests/test_m9_persistent_session_smoke.py -q`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m9_persistent_session_smoke.py --json`

## Commit Target

- `feat: add persistent auth sessions and remember me`

## Outcome

- Implemented the persistent auth-session store, bootstrap restore path, structured gateway session routes, menu bar remembered-session projection, and repository-owned smoke script described in this transaction.
- Final verification and coverage:
  - control-plane changed-line coverage: `99.15%` (`1047/1056`)
  - menu bar changed-line coverage: `100.00%` (`183/183`)
  - Python integration and smoke changed-line coverage: `95.48%` (`190/199`)
  - aggregate changed-line coverage for the touched executable scope: `98.75%` (`1420/1438`)
