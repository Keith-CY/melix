# Chat Light Workspace

## Goal

Redesign the Melix Chat workspace so the first layer is conversation-first while
preserving local runtime evidence, server binding, and diagnostic traceability.

The redesign makes Chat read as a lightweight native chat surface by default:
the transcript becomes the primary visual object, runtime controls move close to
the composer, reasoning and tool activity stay inline with the conversation, and
artifact previews use the existing Inspector side of the layout without
permanently displacing runtime evidence.

## Non-Goals

- Do not change protobuf schemas, worker streaming semantics, or control-plane
  request routing.
- Do not add a new top-level desktop domain.
- Do not introduce a web frontend or non-SF-Symbol icon set into the macOS app.
- Do not implement a full HTML live-preview sandbox in the first slice.
- Do not remove the selected-object Inspector contract from the desktop shell.

## Context

- Relevant specs:
  - `AGENTS.md`
  - `docs/window-ui-product-spec.md`
  - `docs/design-system/README.md`
  - `docs/runbooks/phase-6-chat-panel.md`
  - `docs/runbooks/agent-ui-walkthrough.md`
  - `docs/superpowers/specs/2026-04-07-chat-workspace-tightening-design.md`
- Relevant code:
  - `apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift`
  - `apps/macos-menubar/Sources/AppMain/Chat/DesktopChatMarkdownView.swift`
  - `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
  - `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
  - `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- Current constraints:
  - Chat remains the default first surface.
  - A chat session must bind to an explicit local or remote server before send.
  - Formal UI copy must use Melix terminology and the existing design system.
  - The existing `.runtime` tree is ignored and can hold walkthrough evidence.

## Assumptions

- The first implementation should be a reviewable product slice, not a full
  rewrite of desktop navigation.
- The center transcript should use a document-like assistant presentation while
  retaining explicit role, reasoning, tool, and error semantics for
  accessibility and tests.
- The composer can own immediate chat-readiness controls without changing the
  source of truth for server sessions or chat submission.
- Preview rail state can be local to the chat view in the first slice; durable
  artifact state remains owned by Jobs, Image, Diagnostics, and their existing
  view-model surfaces.

## Work Plan

1. Add a lightweight chat workspace contract to `DesktopChatView.swift`.
   - Keep the three-pane shell.
   - Make the center workspace visually dominant.
   - Move primary server/runtime readiness affordances toward the composer.
   - Keep the existing session sidebar and Inspector available.

2. Refactor transcript row rendering.
   - Present user entries as right-aligned lightweight bubbles.
   - Present assistant entries as document-style readable text without a colored
     full-width bubble.
   - Present reasoning entries as inline collapsible thinking blocks.
   - Present tool entries as inline collapsible tool activity blocks.
   - Preserve error entries as explicit inline error cards.
   - Preserve sanitization and markdown rendering.

3. Add agent activity state treatment.
   - Streaming reasoning rows show a compact "Thinking..." state.
   - Completed reasoning rows expose a collapsed summary such as
     "Thought recorded".
   - Streaming tool rows show a compact "Calling tool" state.
   - Completed tool rows expose a collapsed summary such as "Tool completed".
   - Expanded detail shows sanitized body text.

4. Refactor the composer into a runtime control strip.
   - Keep the NSView-backed text editor and existing command-return behavior.
   - Move the send and stop affordance into the composer surface.
   - Keep `Clear` available as a low-emphasis action.
   - Add server/model readiness capsule content near the input.
   - Add compact capability icons near the input.
   - Surface `Choose Server`, `Start Server`, `Wake`, or `Resume Server` near
     the input when sending is blocked by server state.

5. Add a preview rail entry point.
   - Add local chat view state for `.inspector` versus `.preview`.
   - Add inline artifact triggers for entries that expose artifact-like paths or
     generated output references.
   - First slice may render a path/report preview placeholder with copyable
     provenance rather than executing HTML.
   - Closing preview returns the right rail to Inspector.

6. Update tests.
   - Add focused Swift view tests for transcript role treatment.
   - Add focused Swift view tests for inline thinking/tool summaries.
   - Add focused Swift view tests for composer runtime controls and blocked
     server actions.
   - Add focused Swift view tests for preview rail switching.
   - Preserve existing transcript, markdown, shortcut, and view-model tests.

7. Verification.
   - Run focused macOS menu bar tests covering changed files.
   - Run `git diff --check origin/main...HEAD`.
   - Run `make swift-test` before handoff or PR.
   - Include an explicit changed-scope coverage and metrics report before any
     commit that changes code. If coverage cannot be measured for the slice,
     record `N/A` with the reason and the focused tests used instead.

## Performance Probes

This change is primarily SwiftUI layout and state presentation. Runtime model
performance is out of scope.

Changed-scope probes:

- Rendering probe: focused Swift view tests must instantiate the chat tab,
  transcript rows, composer, and preview rail without layout exceptions.
- Streaming-state probe: existing chat streaming tests must still prove bursty
  deltas are smoothed and final transcript fidelity is preserved.
- Interaction probe: shortcut tests must still prove command-return sends and
  plain return inserts text.

Success metric:

- The chat transcript remains readable and stable while streaming.
- The composer communicates send readiness without requiring the operator to
  inspect the right rail.
- Runtime evidence remains reachable in the Inspector after preview is closed.

## Acceptance Criteria

- Empty Chat opens with a lightweight center-first layout and a composer-centered
  start state.
- A ready server session can still submit chat through the existing view model.
- A blocked server session exposes the correct runtime recovery action near the
  composer.
- User messages render as right-aligned lightweight bubbles.
- Assistant messages render as readable document-style text.
- Reasoning and tool entries render inline activity summaries and expandable
  details.
- The right rail can switch between Inspector and Preview and return to
  Inspector.
- Existing chat transcript sanitization, markdown rendering, streaming, and
  shortcut behavior remain covered by tests.

## Rollback or Safe Exit

- If the transcript rendering refactor becomes risky, keep the existing
  `DesktopChatTranscriptRowView` data contract and limit the first commit to
  role-specific styling plus tests.
- If preview rail integration becomes too broad, keep artifact triggers as
  disabled view-only rows and defer rail switching to a follow-up plan.
- If composer runtime controls conflict with server lifecycle behavior, keep the
  existing server picker in the header and land only inline capability/readiness
  indicators.
