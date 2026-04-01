# Server Session Product Model

## Goal

Define `Server Session` as the first-class served-runtime product object for the desktop shell and the future control-plane contract.

## Scope

- typed server-session desktop state
- lifecycle states and state transitions
- per-server listener configuration
- `Server` page object model
- control-plane and protocol evolution required for multi-listener truth

## Non-Goals

- using a single gateway-default object as the long-term model
- claiming that the current backend already persists multiple listeners

## Required Model

Each `Server Session` must capture:

- `serverSessionID`
- `servedModelID`
- `host`
- `port`
- `authMode`
- `rateLimit`
- `timeout`
- `servingDefaults`
- `lifecycleState`
- `healthState`
- `lastError`

## Lifecycle

Required typed lifecycle states:

- `draft`
- `starting`
- `running`
- `stopping`
- `stopped`
- `failed`
- `unavailable`

Required transitions:

- `draft -> starting -> running`
- `running -> stopping -> stopped`
- `starting -> failed`
- `running -> failed`
- `failed -> starting`

## Control-Plane Evolution

### Current State

The current control plane exposes a single gateway-style configuration surface.

### Required Evolution

- introduce server-session identifiers
- persist listener configuration per server session
- surface lifecycle and health events for each server session
- expose URL and auth metadata per server session

## Server Page Rules

- left sidebar unit is `Server Session`
- create flow starts with model selection
- main editor shows basic fields immediately
- advanced defaults remain inside disclosure panels
- inspector shows status, URL, errors, copy actions, and object-local shortcuts only

## Files

- modify `apps/macos-menubar/Sources/AppMain/Models/`
- modify `apps/macos-menubar/Sources/AppMain/Dashboard/` and or `Server` page views
- update protocol docs if schema work begins

## Performance Probes

- server-session creation latency
- server-session start latency
- server-session stop latency
- failure-to-banner escalation count

## Verification

- `swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests`
- targeted control-plane tests for server-session lifecycle once protocol work lands

## Acceptance

- the desktop shell has typed server-session state
- server-session editing is distinct from tools and dashboard content
- the `Server` page follows the required creation order
- protocol work items for multi-listener truth are explicitly tracked rather than implied
