# Window UI Information Architecture Refresh Plan

## Status

Accepted IA direction. Formal product specification now lives in
[`../window-ui-product-spec.md`](../window-ui-product-spec.md).

This file is an implementation-planning record. If this plan appears to
conflict with the product spec, the product spec wins.

## Goal

Refresh the Melix desktop window UI so it reads as a local-first AI runtime
operator console while keeping Chat as the default first surface.

The accepted direction is:

```text
Chat
Command Center
Servers
Models
Workflows
Jobs
Diagnostics
API
Image
Settings
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
- server creation split;
- Jobs and artifact-lineage rules;
- first-run local-server simplification;
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
- Command Center is a top-level cockpit, not the home page.
- Servers and Jobs are first-class domains.
- Create Local Server and Add Remote Server are separate pages.
- Add Remote Server is a strict Endpoint, Authentication, Capabilities Test,
  Review flow.
- Chat composer state is runtime-driven in production.
- Inspector state is selected-object driven when an object is selected.
- Selected-object routes support deep links.
- Row selection updates route state with replace semantics.
- Row action navigation carries a meaningful object selection or clears it.
- `pending_review` is review state, not health state.
- API Playground should read as a request/response developer console.
- Advanced local-server fields are collapsed by default for first-run setup.

## First Implementation Slices

The implementation should proceed in small slices rather than a broad UI
rewrite.

1. Route Metadata And Shell Navigation
   - Define route metadata for the 10 top-level domains and secondary pages.
   - Drive sidebar, tabs, title, subtitle, primary action, and Inspector module
     from metadata.
   - Add route state for selected objects.

   Status: initial implementation slice landed. The desktop shell now exposes
   the accepted 10 top-level domains, treats Jobs as a first-class navigation
   surface, defines typed route metadata for the accepted domain/page map, and
   normalizes canonical selected-object route values plus legacy `eval` and
   `token` aliases. Legacy persisted `Tools / Jobs` session state migrates to
   the top-level Jobs surface. Follow-up slices still need to make every header,
   secondary tab, and Inspector panel consume this metadata directly.

2. Inspector Contract
   - Implement page-level and selected-object Inspector modes.
   - Preserve Context, Health, Metrics, Actions, Evidence order.
   - Add visible detail action when a selected object has a detail route.

3. Chat Runtime Contract
   - Keep Chat default.
   - Block send without explicit server binding.
   - Add no-server, degraded, offline, and ready composer states driven by
     runtime status.

4. Servers And Jobs Domains
   - Split Create Local Server and Add Remote Server.
   - Expose server profiles, capability receipts, job queue, job history, and
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
