# Melix Task 5 Execution Plan: Minimal Menu Bar Shell

## Scope

This plan replaces the macOS menu bar placeholder with a real operator-facing shell for phase 0.

The slice remains narrow:

- keep the app focused on control-plane visibility and model operations
- connect through an XPC-shaped client abstraction instead of adding worker-direct access
- hydrate runtime state from control-plane handshake and event subscription
- support load and unload for the development text model

This slice does not add:

- settings persistence
- cache inspector UI
- request history UI
- branch or session visualizations
- real system `NSXPCConnection` transport plumbing

## Architecture Boundaries

- The app remains an operator shell and does not own orchestration logic.
- The app talks only to a `ControlPlaneXPCClient` abstraction.
- The default phase-0 concrete implementation may wrap `ControlPlaneService` directly, but the app surface must remain isolated from control-plane internals behind the client boundary.
- The view model owns app state derivation and command dispatch.
- The status menu owns only minimal menu rendering and user action wiring.

## Planned Changes

### App structure

- Add a `MenuBar` module area with a minimal `StatusMenu` wrapper.
- Add a `Models` area with a `RuntimeViewModel` that owns:
  - handshake hydration
  - model list state
  - selected server state summary
  - load/unload command dispatch
  - event-driven model state refresh
- Add an `XPCClient` area with:
  - `ControlPlaneXPCClient` protocol
  - `LocalControlPlaneXPCClient` phase-0 implementation backed by `ControlPlaneService`
  - a small event-subscription bridge that converts control-plane async streams into app callbacks

### UI behavior

- On launch, the app performs handshake and publishes an initial status label.
- The menu shows:
  - server readiness
  - the development text model state
  - load action when the model is not warm
  - unload action when the model is warm
- The UI refreshes when control-plane model-state events arrive.

### Performance probes and metrics

Required probes for this slice:

- app startup to handshake completion latency
- snapshot hydration latency
- model load command round-trip latency
- model unload command round-trip latency

Initial success targets:

- local handshake and snapshot hydration stay below 100 ms in tests
- load/unload command round trips stay below 150 ms in tests using the local client
- touched app scope reaches at least 95 percent automated coverage before commit

If AppKit timing is not measurable in automated tests, the metrics report may use the view-model/client command path timings instead.

## Verification Plan

Targeted tests:

```bash
swift test --package-path apps/macos-menubar
```

Broader regression checks:

```bash
make swift-test
make coverage
```

## Exit Conditions

Task 5 is complete when:

- the app target is no longer only a placeholder print executable
- the view model hydrates from control-plane handshake
- model load and unload actions dispatch through the client abstraction
- control-plane model-state events update app state
- the menu bar target has tests for hydration, model rendering, actions, and event updates
