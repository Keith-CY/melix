# Task Plan

## Goal

Advance `M13.1` by making gateway listener configuration typed, persistent, and control-plane-owned
across protocol, bootstrap, snapshot projection, and the Window UI server workspace.

## Scope

- extend the control-plane protocol with a typed `server.apply_gateway_config` command and
  `gateway_config` snapshot projection
- persist gateway listener overrides through a control-plane-owned store instead of desktop-only
  session state
- preserve requested versus effective listener configuration after precedence resolution
- migrate desktop host, port, served model, rate limit, and timeout edits onto the control-plane
  apply path
- add focused control-plane and menu-bar coverage for gateway-config persistence, snapshot
  projection, and operator apply flows

## Measurement Points

- `ServerSnapshot.gateway_config` must expose stable listener summaries with requested and
  effective host or port, served model identity, timeout, rate limit, source, and restart status
- gateway listener overrides must persist to a schema-versioned JSON document owned by the control
  plane
- Window UI server edits must apply through the typed control-plane request path and hydrate the
  effective listener state back into desktop session state
- server starts must persist the selected gateway listener configuration before lifecycle mutation

## Phases

1. Typed gateway-config contract and persistence
   - status: completed
   - evidence:
     - added `server.apply_gateway_config`, `GatewayConfigSummary`, and
       `GatewayListenerConfigSummary` to the protocol schema plus regenerated Swift, Python, and
       descriptor outputs
     - added `GatewayConfigStore` so built-in defaults, environment defaults, and operator
       overrides resolve through a control-plane-owned persistence path backed by schema-versioned
       JSON
2. Control-plane projection and bootstrap ownership
   - status: completed
   - evidence:
     - projected `gateway_config` through `ServerSnapshot` and wired listener bootstrap binding
       through the persisted store
     - recorded typed gateway-config metrics for apply latency, persistence failures, and
       restart-required state
3. Desktop apply path and operator visibility
   - status: completed
   - evidence:
     - exposed a typed XPC client `applyServerSessionGatewayConfig(...)` path and server-surface
       `Apply Gateway Config` action in the Window UI
     - projected requested and effective listener state, source, and restart-required badges into
       `DesktopServerSessionState` and the inspector surface
     - persisted selected gateway config automatically before `Start`
4. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - added focused control-plane and menu-bar regression tests for gateway-config summary
       projection, persistence failures, typed request construction, and desktop apply or start
       flows
     - recorded changed-line coverage at or above `95%`, updated `progress.md`, and closed `M13.1`
       in the roadmap execution index

## Acceptance

- gateway listener configuration is typed, persistent, and inspectable through supported product
  surfaces
- the control plane owns listener-configuration truth for host, port, served model, timeout, and
  rate limit fields projected in `ServerSnapshot`
- Window UI gateway edits flow through the typed control-plane path and preserve requested versus
  effective listener divergence when a restart is required

## Risks

- listener precedence could drift between bootstrap and snapshot projection if runtime binding is
  not derived from the same persisted source of truth
- desktop edits could regress into local-only state if starts mutate lifecycle before listener
  persistence succeeds
- requested versus effective listener state could become misleading if non-active sessions are
  flattened into one global listener view

## Outcome

- m13_1_completed
