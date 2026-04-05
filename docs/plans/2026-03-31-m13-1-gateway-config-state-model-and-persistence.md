# M13.1 Gateway Config State Model And Persistence

## Goal

Define the typed gateway-configuration model and persistence flow used by the control plane and desktop shell.

Status: completed on 2026-04-05.

This slice closes the current gap where gateway access policy is owned by the control plane, but listener configuration
such as host, port, served model identity, rate-limit draft, and timeout draft still live only inside desktop-session
state.

## Scope

- add a typed gateway-config command and snapshot projection for listener configuration
- persist operator listener edits through a control-plane-owned store instead of desktop-only session state
- keep requested and effective listener settings inspectable after precedence resolution
- migrate desktop host, port, served-model, rate-limit, and timeout editing to the control-plane path

## Non-Goals

- live listener rebind for host or port changes inside the current process
- batching, generation defaults, speculative decoding, embedding, MCP, or config-file argument controls
- merging gateway-access secrets into the new gateway-config summary; auth remains projected through `gateway_access`
- multi-listener runtime serving semantics; this slice only establishes the typed state model and persistence path

## Typed Contract

Add a new `server.apply_gateway_config` command and a typed snapshot projection:

- `ApplyGatewayConfig`
  - `server_session_id`
  - `host`
  - `port`
  - `served_model_id`
  - `rate_limit_per_minute`
  - `timeout_seconds`
- `GatewayConfigSummary`
  - repeated `GatewayListenerConfigSummary`
- `GatewayListenerConfigSummary`
  - `server_session_id`
  - `requested_host`
  - `requested_port`
  - `effective_host`
  - `effective_port`
  - `served_model_id`
  - `rate_limit_per_minute`
  - `timeout_seconds`
  - `source`
  - `active_binding`
  - `requires_restart`
  - `updated_at_unix_ms`
- `GatewayConfigSource`
  - `built_in_defaults`
  - `environment_defaults`
  - `config_file_import`
  - `operator_override`

`ServerSnapshot` must carry `gateway_config` alongside the existing `gateway_access` summary.

## Precedence Model

For this slice, listener configuration resolves in this order:

1. built-in defaults
2. environment defaults
3. persisted config-file imports
4. persisted operator overrides

`effective_host` and `effective_port` must reflect the currently active bootstrap listener binding for the active
gateway server session. If operator edits request a different host or port while the process is already running, the
snapshot must preserve the requested values, keep the effective binding unchanged, and mark `requires_restart = true`.

For `served_model_id`, `rate_limit_per_minute`, and `timeout_seconds`, the snapshot should expose the resolved control-
plane truth directly for the selected server session in this slice.

## Implementation Slices

### Slice 1

- add the proto messages and generated artifacts
- add a control-plane-owned `GatewayConfigStore`
- persist operator overrides to Application Support with a schema-versioned JSON document
- project `gateway_config` through `ServerSnapshot`
- add a typed `applyGatewayConfig` client path and desktop `Apply Gateway Config` action
- automatically persist selected server-session config before `Start`

### Deferred To Later M13 Slices

- generation defaults, batching, speculative decoding
- embedding, tool-parser, MCP, config-file path, additional arguments
- API onboarding and quick-start material

## Files

- update `packages/protocol/schema/controlplane/v1/control_plane.proto`
- update generated protocol outputs under `packages/protocol/swift/controlplane/v1/` and `packages/protocol/python/controlplane/v1/`
- add or update `services/control-plane-swift/Sources/HTTPGateway/`
- update `services/control-plane-swift/Sources/Snapshots/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `services/control-plane-swift/Sources/Bootstrap/main.swift`
- update `apps/macos-menubar/Sources/AppMain/Models/`
- update `apps/macos-menubar/Sources/AppMain/Dashboard/`
- add or update focused tests under `services/control-plane-swift/Tests/ControlPlaneTests/` and `apps/macos-menubar/Tests/MenuBarTests/`

## Implementation Notes

- persistence must preserve explicit operator edits and later config-file imports without leaking auth material
- requested versus effective host and port must remain visible after precedence resolution
- config fields must remain reusable across API and desktop surfaces
- gateway access secrets continue to flow through `GatewayAccessPolicyStore`; the new store owns listener configuration only

## Key Probes

- `gateway.config_apply_ms`
- `gateway.config_round_trip_ms`
- `gateway.config_persist_failures`
- `gateway.config_requires_restart_count`

## Verification

- `make proto`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|GatewayConfigStoreTests'`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
- changed-line coverage for touched Swift files must be `>=95%`
- `git diff --check`

## Acceptance

- gateway listener configuration is typed, persistent, and inspectable through supported product surfaces
- the control plane owns the listener-configuration truth projected in `ServerSnapshot`
- desktop host, port, served model, rate limit, and timeout edits can flow through the control-plane path
- requested and effective host or port divergence remains visible when a restart is required

## Outcome

- delivered `server.apply_gateway_config`, `GatewayConfigSummary`, and typed desktop apply actions
- persisted listener overrides through `GatewayConfigStore` and bootstrap-backed precedence resolution
- closed `M13.1` with focused Swift changed-line coverage at `97.31%` (`795/817`) aggregate for the
  touched handwritten scope
