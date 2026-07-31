# Remote Provider Chat Binding

## Goal

Make every configured Remote Provider visible and usable in the macOS Chat
Provider picker while preserving the existing Local Provider lifecycle and
model-loading behavior.

The governing product contract is `docs/window-ui-product-spec.md`: a Chat
session binds to one explicit Local or Remote Provider before sending. The
existing direct-target transport in
`docs/plans/2026-04-27-remote-server-direct-target.md` remains authoritative
for Remote Provider request construction and secret handling.

## Current Failure

The Providers workspace already exposes a unified `providerTargets` collection,
and the control plane already accepts `ControlPlaneChatRequest.remoteTarget`.
Desktop Chat bypasses both interfaces:

- `DesktopChatSessionState` stores only a Local Provider Server Session ID;
- the Chat picker enumerates only `serverSessions`;
- binding rejects IDs that do not resolve to a Local Provider Server Session;
- submission performs Local Provider readiness and model-loading checks before
  it can construct a request.

As a result, a successfully saved Remote Provider cannot appear in the Chat
picker or reach the existing remote dispatch path.

## End-State Architecture

1. Introduce a small typed Provider target reference that owns stable
   `local:<id>` and `remote:<id>` identity parsing and formatting.
2. Store that reference on each Chat session. The Chat session does not store
   credentials or duplicate Provider metadata.
3. Make the Runtime View Model the single module that resolves a Chat Provider
   target into Local or Remote behavior:
   - Local targets retain lifecycle admission, model availability checks, and
     on-demand model loading.
   - Remote targets load their API key only when submitting, construct the
     existing `ControlPlaneChatRequest.RemoteTarget`, and bypass Local Provider
     lifecycle and model-loading work.
4. Make the Chat picker, model identity, readiness gate, capabilities, and
   Inspector consume the same selected Provider target presentation.
5. Keep Local Provider lifecycle repair actions local-only. Remote Provider
   configuration or credential failures route operators back to Providers.

This creates one deep Chat Provider binding module in `RuntimeViewModel`: views
learn one target identity and one readiness result, while Local and Remote
dispatch details remain behind that interface.

## Delivery Slices

1. Add regression tests that prove a saved Remote Provider appears in Chat,
   can be bound to a Chat session, and produces a remote chat request without a
   Local Provider Server Session.
2. Add the typed Provider target reference and migrate Chat session binding,
   fork, restoration, and invalidation behavior.
3. Route submission through Local and Remote request construction, including
   missing-credential and missing-model failures.
4. Update Chat presentation to use unified Provider identity and readiness,
   while preserving Local Provider repair actions.
5. Update the canonical UI specification and run focused, coverage, full-gate,
   and performance verification.

## Compatibility And Security

- Existing Local Provider Chat behavior and request Server Session IDs remain
  unchanged.
- Remote Provider API keys stay in the Remote Provider secret store and enter
  only the in-process control-plane request. They never enter Chat session
  state, transcripts, logs, or exported Markdown.
- Provider target IDs are stable, type-qualified values so a Local and Remote
  Provider may safely share the same underlying ID.

## UI Walkthrough Decision

No walkthrough artifact is required for this slice. It does not introduce a
new layout, control, navigation flow, or visual language. It makes the existing
Provider picker and identity surfaces honor the already accepted Local/Remote
Provider product contract.

## Performance And Observability

- Observability mode: `minimal`; no new debug or evidence-mode artifacts.
- Measurement point: existing `menu.chat_submit_ms`, measured from submit entry
  through control-plane execution creation for both Local and Remote targets.
- Selection and binding remain in-memory linear scans over the already rendered
  Provider collection. Secret-store I/O occurs only on Remote Provider submit,
  never during SwiftUI rendering.
- Success metrics:
  - Remote submission performs zero Local Provider lifecycle, catalog refresh,
    or model preload operations before `startChat`.
  - Local submission preserves its existing request shape and lifecycle checks.
  - Focused Chat tests remain deterministic and complete in under one second
    after the Swift package is built.
  - The repository pre-commit performance report reports no in-scope
    regression; if no macOS Chat probe is selected, record performance as
    `N/A` with the existing `menu.chat_submit_ms` measurement point retained.

## Verification

Run at minimum:

```bash
xcrun swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests
xcrun swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests
make swift-coverage
make swift-test
make py-test
make integration-test
```

Before each commit, allow the versioned pre-commit hook to run the required
full local gate and scoped performance report on this host.

