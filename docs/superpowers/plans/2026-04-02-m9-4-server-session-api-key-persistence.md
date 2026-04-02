# M9.4 Server-Session API Key Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `Server Session` the persisted owner of a primary API key, apply that key to the active single Melix gateway through a typed control-plane mutation, and move product-owned local state from `~/Library/Application Support/Melix` to `~/.melix`.

**Architecture:** Add a typed server-side gateway-access apply command plus a mutable runtime policy store in the Swift control plane. Add a `MELIX_HOME`-backed persistence layer in the macOS operator app for non-secret restore state and per-session primary API keys, then wire the existing `Server Session` surface to generate, reveal, copy, persist, and apply those keys. Update productization scripts, runbooks, and smoke coverage so App and future CLI share the same `~/.melix` layout.

**Tech Stack:** Swift 6, Swift Testing, SwiftUI, protobuf schemas and generated artifacts, Python 3, pytest, repository-owned smoke scripts.

---

## Scope Notes

- This plan supersedes the remember-me direction in `docs/plans/2026-03-30-m9-4-persistent-sessions-and-remember-me.md`.
- This slice does not implement account auth, sign-in, sign-out, remote identity, or Keychain storage.
- This slice keeps the current single HTTP listener. A persisted primary key is applied only when its `Server Session` is the active runtime session.
- Use frequent commits after each task. Do not batch Tasks 1 through 5 into one commit.

## File Structure

- `packages/protocol/schema/controlplane/v1/control_plane.proto`
  - Add the typed server command for applying gateway access from a server-session-scoped payload.
- `services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayAccessPolicyStore.swift`
  - New mutable runtime store that owns the effective in-memory `GatewayAccessPolicy`.
- `services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayAccessPolicy.swift`
  - Keep policy normalization and summary projection, but support runtime application from typed records instead of bootstrap-only environment loading.
- `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
  - Accept the new typed server command and rebuild effective gateway policy and snapshot state.
- `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
  - Authorize requests against the shared runtime policy store rather than a frozen bootstrap policy.
- `apps/macos-menubar/Sources/AppMain/Persistence/MelixHome.swift`
  - Resolve `MELIX_HOME`, default directories, and file permissions for the app.
- `apps/macos-menubar/Sources/AppMain/Persistence/OperatorSessionStore.swift`
  - Persist non-secret local operator restore state to `~/.melix/state/operator-session.json`.
- `apps/macos-menubar/Sources/AppMain/Persistence/ServerSessionAPIKeyStore.swift`
  - Persist per-session primary API keys to `~/.melix/secrets/server-session-api-keys.json`.
- `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
  - Own restore, persist, secure key generation, active-session apply, reveal, and copy behaviors.
- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
  - Render the masked field, eye or copy icons inside the input, and refresh icon outside the input.
- `services/mlx-worker-python/worker/productization/melix_home.py`
  - New shared Python helper that defines the `~/.melix` layout for install assets and app bundle scripts.
- `services/mlx-worker-python/worker/productization/install_assets.py`
  - Stop writing install artifacts to Application Support and emit `MELIX_HOME`-based layout instead.
- `services/mlx-worker-python/worker/productization/macos_app_bundle.py`
  - Stop exporting `MELIX_APP_SUPPORT_DIR`; export `MELIX_HOME` and derive runtime or logs from it.
- `scripts/m9_server_session_api_key_smoke.py`
  - Deterministic repository-owned smoke that verifies the typed apply path, local persistence pathing, and `~/.melix` layout.

## Performance Probes And Success Metrics

- `operator.session_restore_ms`
- `operator.session_persist_write_ms`
- `gateway.api_key_apply_ms`
- `gateway.api_key_persist_failures`

## Task 1: Add A Typed Gateway-Access Apply Command And Mutable Runtime Policy Store

**Files:**
- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
- Modify: `packages/protocol/swift/controlplane/v1/control_plane.pb.swift`
- Modify: `packages/protocol/python/controlplane/v1/control_plane_pb2.py`
- Modify: `packages/protocol/descriptors/melix.pb`
- Create: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayAccessPolicyStore.swift`
- Modify: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayAccessPolicy.swift`
- Modify: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- Modify: `services/control-plane-swift/Sources/Bootstrap/main.swift`
- Modify: `services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`

- [ ] Add failing Swift tests in `ControlPlaneServiceTests.swift` for `server.apply_gateway_access` with these cases:
  - applying `api_keys` for `server-session-1` publishes a redacted snapshot with `accepted_api_key_count == 1`
  - applying `none` clears the runtime policy back to local trust
  - plaintext `primary_key` never appears in snapshot `token_hint` values
- [ ] Add a failing `OpenAIHandlerTests.swift` case proving a shared `GatewayAccessPolicyStore` can move `/v1/models` from `401 missing_api_key` to `200` after an apply command changes the active runtime policy.
- [ ] Run the focused control-plane tests and confirm failure:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'applyGatewayAccess|gatewayAccessPolicy|handshakeProjectsGatewayAccessSummaryWithoutLeakingRawSecrets|getModelsUsesRuntimeGatewayAccessPolicyStore'`
- [ ] Update `control_plane.proto` to add a typed server command payload for applying gateway access from a server-session-scoped request. The payload should include:
  - `server_session_id`
  - `mode`
  - `shared_access_enabled`
  - one primary key record containing `key_id`, `label`, `token_hint`, and `token`
- [ ] Run `make proto` to regenerate the Swift, Python, and descriptor artifacts.
- [ ] Implement `GatewayAccessPolicyStore.swift` as the single mutable runtime authority, inject it into `Bootstrap/main.swift`, `ControlPlaneService.swift`, and `OpenAIHandler.swift`, and record `gateway.api_key_apply_ms` whenever the typed apply command succeeds.
- [ ] Update `ControlPlaneService.swift` so `server.get_snapshot` and handshake both read the current store value instead of a frozen bootstrap policy.
- [ ] Re-run the focused control-plane tests and confirm they pass.
- [ ] Commit Task 1:
  - `git add packages/protocol/schema/controlplane/v1/control_plane.proto packages/protocol/swift/controlplane/v1/control_plane.pb.swift packages/protocol/python/controlplane/v1/control_plane_pb2.py packages/protocol/descriptors/melix.pb services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayAccessPolicyStore.swift services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayAccessPolicy.swift services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Sources/Bootstrap/main.swift services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`
  - `git commit -m "feat: add runtime gateway access mutation"`

## Task 2: Add `MELIX_HOME`-Backed Operator Persistence And Active-Session Apply Logic

**Files:**
- Create: `apps/macos-menubar/Sources/AppMain/Persistence/MelixHome.swift`
- Create: `apps/macos-menubar/Sources/AppMain/Persistence/OperatorSessionStore.swift`
- Create: `apps/macos-menubar/Sources/AppMain/Persistence/ServerSessionAPIKeyStore.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/AppMain.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/XPCClient/ControlPlaneXPCClient.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/AppMainBootstrapTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`

- [ ] Add failing tests for `MelixHome` path resolution and permissions with these expectations:
  - default home resolves to `$HOME/.melix`
  - `MELIX_HOME` overrides the default path
  - state or secrets files are created with `0600`
  - parent directories are created with `0700`
- [ ] Add failing `RuntimeViewModelTests.swift` cases for:
  - restoring `selectedSurface` and `selectedServerSessionID` from `operator-session.json`
  - generating a primary key for the selected server session and forcing `authMode == .apiKeys`
  - deferring gateway apply when the selected server session is not running
  - applying the stored key when the selected running server session becomes active
- [ ] Add a failing `ControlPlaneXPCClientTests.swift` case for a typed `applyServerSessionGatewayAccess(...)` client method that builds `server.apply_gateway_access`.
- [ ] Run the focused menu bar tests and confirm failure:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'MelixHome|applyServerSessionGatewayAccess|restoresSelectedSurfaceAndServerSession|generatesPrimaryAPIKeyForSelectedServerSession|appliesStoredKeyWhenSelectedRunningServerSessionBecomesActive'`
- [ ] Implement `MelixHome.swift`, `OperatorSessionStore.swift`, and `ServerSessionAPIKeyStore.swift` with `Codable`, atomic replace writes, and explicit permission handling.
- [ ] Update `AppMain.swift` to resolve `MELIX_HOME` once and inject the new stores into `RuntimeViewModel`.
- [ ] Extend `ControlPlaneXPCClient.swift` and its test doubles so the menu bar can send the new typed apply command.
- [ ] Update `RuntimeViewModel.swift` to:
  - restore operator state on startup
  - persist operator state when selection or local server-session metadata changes
  - generate `melix_sk_...` keys using cryptographically secure random bytes
  - persist the primary key per `serverSessionID`
  - apply the key immediately only when the selected server session is the active running session
  - re-apply the stored key when a different running server session becomes active
  - record `operator.session_restore_ms`, `operator.session_persist_write_ms`, and `gateway.api_key_persist_failures`
- [ ] Re-run the focused menu bar tests and confirm they pass.
- [ ] Commit Task 2:
  - `git add apps/macos-menubar/Sources/AppMain/Persistence/MelixHome.swift apps/macos-menubar/Sources/AppMain/Persistence/OperatorSessionStore.swift apps/macos-menubar/Sources/AppMain/Persistence/ServerSessionAPIKeyStore.swift apps/macos-menubar/Sources/AppMain/AppMain.swift apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Sources/AppMain/XPCClient/ControlPlaneXPCClient.swift apps/macos-menubar/Tests/MenuBarTests/AppMainBootstrapTests.swift apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`
  - `git commit -m "feat: persist operator state and server-session API keys"`

## Task 3: Add Server-Session Primary API-Key Controls In The Desktop Shell

**Files:**
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`

- [ ] Add failing `RuntimeViewModelTests.swift` cases for:
  - masked-by-default primary-key rendering
  - eye-toggle reveal and hide behavior
  - copy action returning the plaintext primary key only when one exists
  - refresh action replacing the key and forcing `authMode == .apiKeys`
- [ ] Add failing `DesktopFoundationViewTests.swift` coverage for the new `Server Session` auth field so the view tree contains:
  - a masked input state
  - an eye icon control
  - a copy icon control
  - a refresh icon button outside the input row
- [ ] Run the focused desktop tests and confirm failure:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'primaryAPIKey|gatewayAccessSummaryAndAuthGuidance|serverSessionAuthField'`
- [ ] Update `DesktopShellState.swift` and `RuntimeViewModel.swift` to expose UI-ready state for:
  - whether a stored primary key exists
  - whether the selected key is currently revealed
  - the masked display value
  - the plaintext value for copy or reveal only when explicitly requested
- [ ] Modify `DesktopWorkspaceShellView.swift` so the `Server Session` auth editor renders the final interaction model:
  - masked field by default
  - eye and copy icons inside the field
  - refresh icon outside the field on the trailing edge
  - generate or refresh triggers persistence plus runtime apply when the selected session is active
- [ ] Update auth guidance strings so `Server Session` and `API` surfaces explain the selected session's effective key semantics without pretending each session already has its own listener.
- [ ] Re-run the focused desktop tests and confirm they pass.
- [ ] Commit Task 3:
  - `git add apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
  - `git commit -m "feat: add server session API key controls"`

## Task 4: Move Product-Owned Local Paths To `~/.melix` And Update Operator Docs

**Files:**
- Create: `services/mlx-worker-python/worker/productization/melix_home.py`
- Create: `services/mlx-worker-python/tests/test_melix_home.py`
- Modify: `services/mlx-worker-python/worker/productization/install_assets.py`
- Modify: `services/mlx-worker-python/worker/productization/macos_app_bundle.py`
- Modify: `services/mlx-worker-python/tests/test_install_assets.py`
- Modify: `services/mlx-worker-python/tests/test_macos_app_bundle.py`
- Create: `docs/runbooks/server-session-api-keys.md`
- Modify: `docs/runbooks/shared-access.md`
- Modify: `docs/runbooks/phase-8-local-install.md`
- Modify: `README.md`

- [ ] Add failing Python tests proving the productization layer now resolves these paths under `~/.melix`:
  - `install/install-manifest.json`
  - `env/melix-product-env.sh`
  - `runtime/`
  - `logs/`
- [ ] Add failing Python tests for the app bundle environment script expecting `MELIX_HOME="$HOME/.melix"` and no `MELIX_APP_SUPPORT_DIR`.
- [ ] Run the focused Python tests and confirm failure:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_melix_home.py services/mlx-worker-python/tests/test_install_assets.py services/mlx-worker-python/tests/test_macos_app_bundle.py -q`
- [ ] Implement `melix_home.py` and refactor `install_assets.py` or `macos_app_bundle.py` to share the same `MELIX_HOME` layout and env exports.
- [ ] Update `README.md`, `docs/runbooks/phase-8-local-install.md`, `docs/runbooks/shared-access.md`, and add `docs/runbooks/server-session-api-keys.md` with:
  - the `~/.melix` directory map
  - primary-key generation and copy guidance
  - the fact that raw secrets remain local-only and snapshot-safe
  - the fact that no compatibility or automatic migration from Application Support is provided
- [ ] Re-run the focused Python tests and spot-check the updated docs for `~/Library/Application Support/Melix` references.
- [ ] Commit Task 4:
  - `git add services/mlx-worker-python/worker/productization/melix_home.py services/mlx-worker-python/tests/test_melix_home.py services/mlx-worker-python/worker/productization/install_assets.py services/mlx-worker-python/worker/productization/macos_app_bundle.py services/mlx-worker-python/tests/test_install_assets.py services/mlx-worker-python/tests/test_macos_app_bundle.py docs/runbooks/server-session-api-keys.md docs/runbooks/shared-access.md docs/runbooks/phase-8-local-install.md README.md`
  - `git commit -m "feat: migrate Melix local home to ~/.melix"`

## Task 5: Add Deterministic Smoke Coverage, Coverage Gates, And Final Verification

**Files:**
- Create: `scripts/m9_server_session_api_key_smoke.py`
- Create: `tests/test_m9_server_session_api_key_smoke.py`
- Modify: `tests/integration/helpers.py`
- Create: `tests/integration/test_server_session_api_key.py`

- [ ] Add a failing deterministic smoke path that proves all of the following:
  - a typed control-plane apply command can switch the active runtime gateway to a generated primary API key
  - `/v1/models` rejects missing credentials after apply and accepts the generated key
  - a temporary `MELIX_HOME` receives `state/` and `secrets/` artifacts in the expected layout
  - productization helpers no longer emit Application Support paths
- [ ] Add a failing `tests/test_m9_server_session_api_key_smoke.py` module that imports the smoke script and verifies JSON output plus timeout handling, matching the existing smoke-script test pattern.
- [ ] Run the smoke-specific pytest command and confirm failure:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest tests/test_m9_server_session_api_key_smoke.py tests/integration/test_server_session_api_key.py -q`
- [ ] Implement the smoke script and update `tests/integration/helpers.py` so `LiveMelixStack` accepts a `melix_home: Path | None` parameter and exports `MELIX_HOME` into every spawned worker and control-plane process.
- [ ] Run final targeted verification:
  - `make proto`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'applyGatewayAccess|gatewayAccessPolicy|handshakeProjectsGatewayAccessSummaryWithoutLeakingRawSecrets|getModelsUsesRuntimeGatewayAccessPolicyStore'`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'MelixHome|applyServerSessionGatewayAccess|primaryAPIKey|gatewayAccessSummaryAndAuthGuidance|restoresSelectedSurfaceAndServerSession|generatesPrimaryAPIKeyForSelectedServerSession|appliesStoredKeyWhenSelectedRunningServerSessionBecomesActive|serverSessionAuthField'`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" COVERAGE_FILE=/tmp/m9_4_python.coverage UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest services/mlx-worker-python/tests/test_melix_home.py services/mlx-worker-python/tests/test_install_assets.py services/mlx-worker-python/tests/test_macos_app_bundle.py tests/test_m9_server_session_api_key_smoke.py tests/integration/test_server_session_api_key.py -q`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" COVERAGE_FILE=/tmp/m9_4_python.coverage UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /tmp/m9_4_python_coverage.json`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m9_server_session_api_key_smoke.py --json`
- [ ] Measure changed-line coverage for the touched Swift scope:
  - `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayAccessPolicyStore.swift services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayAccessPolicy.swift services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Sources/Bootstrap/main.swift services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Persistence/MelixHome.swift apps/macos-menubar/Sources/AppMain/Persistence/OperatorSessionStore.swift apps/macos-menubar/Sources/AppMain/Persistence/ServerSessionAPIKeyStore.swift apps/macos-menubar/Sources/AppMain/AppMain.swift apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Sources/AppMain/XPCClient/ControlPlaneXPCClient.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- [ ] Measure changed-line coverage for the touched Python scope:
  - `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m9_4_python_coverage.json services/mlx-worker-python/worker/productization/melix_home.py services/mlx-worker-python/tests/test_melix_home.py services/mlx-worker-python/worker/productization/install_assets.py services/mlx-worker-python/worker/productization/macos_app_bundle.py scripts/m9_server_session_api_key_smoke.py tests/integration/test_server_session_api_key.py tests/test_m9_server_session_api_key_smoke.py`
- [ ] Record the changed-scope metrics report for:
  - `operator.session_restore_ms`
  - `operator.session_persist_write_ms`
  - `gateway.api_key_apply_ms`
  - `gateway.api_key_persist_failures`
- [ ] Commit Task 5:
  - `git add scripts/m9_server_session_api_key_smoke.py tests/test_m9_server_session_api_key_smoke.py tests/integration/helpers.py tests/integration/test_server_session_api_key.py`
  - `git commit -m "test: add M9.4 smoke coverage and verification"`
