# Window UI Information Architecture Refresh Plan

## Status

Accepted IA direction. Formal product specification now lives in
[`../window-ui-product-spec.md`](../window-ui-product-spec.md).

This file is an implementation-planning record. If this plan appears to
conflict with the product spec, the product spec wins.

## Goal

Refresh the Melix desktop window UI so it reads as a local-first AI runtime
operator console while keeping Chat as the default first surface.

The accepted routable IA is:

```text
Chat
Command Center
Providers
Models
Workflows
Jobs
Diagnostics
API
Image
Settings
```

The titlebar primary navigation is intentionally limited to:

```text
Chat
Providers
Models
Workflows
```

## Governing Spec

Implementation slices must follow
[`docs/window-ui-product-spec.md`](../window-ui-product-spec.md), including:

- product object terminology;
- health, execution, and review-state vocabularies;
- route and selected-object behavior;
- Inspector contract;
- inbound and outbound credential boundaries;
- Chat runtime-binding rules;
- provider creation split;
- Jobs and artifact-lineage rules;
- first-run local-provider simplification;
- visual-system constraints.

## Walkthrough Evidence

The accepted disposable walkthrough artifacts were created under
`.runtime/walkthrough/` during operator review. They are not committed by
default because `.runtime` artifacts are review evidence, not production source.

The latest reviewed artifact path was:

```text
.runtime/walkthrough/window-ui-ia-refresh-v3.html
```

The walkthrough established these durable decisions:

- Chat remains the default first surface.
- Command Center is a routable cockpit, not the home page.
- Providers and Jobs are first-class domains.
- Create Local Provider and Add Remote Provider are separate pages.
- Add Remote Provider is a strict Endpoint, Authentication, Capabilities Test,
  Review flow.
- Chat composer state is runtime-driven in production.
- Inspector state is selected-object driven when an object is selected.
- Selected-object routes support deep links.
- Row selection updates route state with replace semantics.
- Row action navigation carries a meaningful object selection or clears it.
- `pending_review` is review state, not health state.
- API Playground should read as a request/response developer console.
- Advanced local-provider fields are collapsed by default for first-run setup.

## First Implementation Slices

The implementation should proceed in small slices rather than a broad UI
rewrite.

1. Route Metadata And Shell Navigation
   - Define route metadata for the 10 routable domains and secondary pages.
   - Drive sidebar, tabs, title, subtitle, primary action, and Inspector module
     from metadata.
   - Add route state for selected objects.

   Status: initial implementation slice landed. The desktop shell now exposes
   the accepted 10 routable domains, treats Jobs as a first-class navigation
   surface, defines typed route metadata for the accepted domain/page map, and
   normalizes canonical selected-object route values. Legacy persisted `Tools /
   Jobs` session state migrates to the routable Jobs surface. Follow-up slices
   still need to make every header, secondary tab, and Inspector panel consume
   this metadata directly.

   Status: titlebar follow-up now keeps only Chat, Providers, Models, and
   Workflows in primary navigation while preserving screenshot coverage and
   route metadata for Command Center, Jobs, Diagnostics, API, Image, and
   Settings.

   Status: selected-object route follow-up now makes `provider:<id>` the
   Provider Profile route kind, rejects legacy selected-object aliases, and
   gives route-action targets an optional selected-object payload so detail
   links and Inspector actions can carry selection through typed metadata
   instead of string-built URLs.

2. Inspector Contract
   - Implement page-level and selected-object Inspector modes.
   - Preserve Context, Health, Metrics, Actions, Evidence order.
   - Add visible detail action when a selected object has a detail route.

   Status: review follow-up for the route metadata shell slice now maps Jobs
   domain Inspector evidence from the selected job root, logs, and every fetched
   artifact path so artifact lineage is not truncated to the first artifact.

3. Chat Runtime Contract
   - Keep Chat default.
   - Block send without explicit provider binding.
   - Add no-provider, degraded, offline, and ready composer states driven by
     runtime status.

   Status: provider status strip follow-up now renders provider health and
   model-capability readiness as fixed-width colored icon plus short-code
   signals. Visible strip text stays compact; full provider, model, and runtime
   detail moves to help text, accessibility labels, and selected-object detail.
   The compact strip is intentionally a space-saving status-light treatment,
   not a place for expanded metric readouts.

   Status: composer repair follow-up now replaces the text input for blocking
   provider states with one primary repair action: Choose Provider, Attach
   Model, Start Provider, Resume Provider, Open Providers, or Run Capabilities
   Test. Degraded providers keep the text input and expose `Send Anyway` plus a
   compact Providers repair entry. Screenshot capture now includes no-provider,
   missing-model, offline-provider, and degraded-provider Chat composer states.

4. Providers And Jobs Domains
   - Split Create Local Provider and Add Remote Provider.
   - Expose provider profiles, capability receipts, job queue, job history, and
     artifact lineage.

5. Domain Polish
   - Apply the visual signatures and domain layouts from the product spec.
   - Update screenshot capture coverage for the new shell.

## Verification Plan

Documentation-only baseline:

```bash
git diff --check
```

Implementation slices must add focused Swift tests before production UI edits,
then run the relevant scoped commands. At minimum:

```bash
swift test --package-path apps/macos-menubar
git diff --check
```

Before a PR that touches executable UI code, include coverage and metrics for
the changed scope. For this spec-only baseline, coverage and metrics are `N/A`
because no executable code changes.

## Known Gaps

- This plan does not choose final SwiftUI component names.
- The first implementation slice must resolve the final route metadata type
  against existing `DesktopShellState` and `RuntimeViewModel` code.
- Screenshot capture expectations must be updated when production UI changes
  begin.
- The runtime walkthrough files remain untracked unless the operator explicitly
  asks to commit them.
