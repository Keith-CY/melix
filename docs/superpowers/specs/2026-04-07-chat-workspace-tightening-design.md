# Chat Workspace Tightening Design

## Summary

Melix should tighten the desktop chat workspace so it behaves more like a compact native utility
surface and less like a wide three-column dashboard. The current chat page spends too much space
on tall title-bar tabs, oversized side panels, a large composer, and heavyweight inline controls.

The approved direction is:

- keep the native title-bar tab placement, but make the tab control materially shorter so it fits
  cleanly inside the macOS title bar
- reduce the default widths of the chat-session sidebar and the inspector column
- keep both side columns expanded by default, but let each one collapse into a slim persistent rail
  instead of disappearing entirely
- shrink the chat composer to roughly a three-line default height
- move session-specific `Fork` and `Export` actions out of the main workspace header and into the
  selected chat-session row via a compact trailing menu affordance
- reduce the visual weight of the composer container border
- compress the audio-setup notification into a single-row compact notice

## Problem

The current chat workspace has seven concrete UX problems:

1. The title-bar tab control is too tall and visually spills beyond the available title-bar space.
2. The left chat-session column and the right inspector column consume more horizontal space than
   their current content requires.
3. Both side columns can become visually heavy, but the current toggles are body-level buttons
   rather than compact native-feeling collapse controls.
4. The composer reserves too much height for a default empty chat prompt.
5. Session actions such as `Fork` and `Export` occupy prime workspace-header space even though they
   belong to the selected chat session itself.
6. The composer border reads heavier than the surrounding UI and exaggerates the input area.
7. The audio remediation notice consumes two lines and feels oversized for a single urgent action.

Taken together, these issues make the workspace feel taller, wider, and busier than necessary.

## Approaches

### 1. Minimal spacing patch

- Reduce a few paddings and widths.
- Leave the session-action placement and collapse model largely unchanged.

Pros:

- Lowest implementation risk.
- Smallest code delta.

Cons:

- Does not solve the ownership problem for `Fork` and `Export`.
- Leaves the collapse interaction feeling bolted onto the main content.
- Likely still looks oversized after the patch.

Rejected.

### 2. Compact workspace with persistent side rails

- Tighten the title-bar tab control.
- Narrow both side columns.
- Collapse each side column into a slim persistent rail with a clear restore affordance.
- Move session actions into the session row menu.
- Shorten the composer and compact the audio notice.

Pros:

- Reclaims meaningful horizontal and vertical space.
- Keeps collapse affordances visible and discoverable.
- Puts session actions next to the session they operate on.
- Matches the approved visual direction from the layout review.

Cons:

- Touches title-bar chrome, chat layout, and session-row interactions together.
- Requires careful SwiftUI layout tuning to avoid regressions.

Recommended.

### 3. Fully hide side columns when collapsed

- Collapse side columns completely and restore them only through top-level buttons.

Pros:

- Maximizes center-column space.
- Simplest visual state when collapsed.

Cons:

- Weaker discoverability once the side columns are hidden.
- Makes the chat workspace feel mode-driven instead of continuously inspectable.

Rejected.

## Recommended Design

### Title-Bar Tabs

Keep the tab switcher in the native title bar. Reduce its vertical footprint by tightening:

- control height
- vertical padding
- capsule insets
- label font sizing only if required after spacing changes

The result should remain legible but must no longer protrude below the title-bar rhythm established
by macOS traffic lights and native toolbar controls.

### Chat Layout Widths

Adjust the default chat layout to use a narrower three-pane balance:

- chat-session sidebar target width: approximately `210` to `230`
- inspector target width: approximately `220` to `240`
- center workspace receives the recovered width

These values are directional rather than hard requirements. The implementation should preserve
comfortable reading width for the center transcript and composer.

### Persistent Collapse Rails

Both side columns stay expanded by default. When collapsed, each one becomes a slim vertical rail
that remains visible at the workspace edge. Each rail should:

- occupy only a small amount of width
- expose a clear affordance to reopen the corresponding column
- feel like part of the native split layout rather than a floating overlay

The main chat header may still include compact visibility toggles, but the rails themselves must
remain sufficient for re-expansion so the layout never becomes undiscoverable.

### Session Row Ownership

`Fork` and `Export` move from the main chat workspace header into the selected chat-session row.

The session row should gain a compact trailing action area, using icon-plus-menu treatment or a
single compact menu trigger, as long as it:

- clearly belongs to the session item
- stays on one line
- does not materially increase row height

The workspace header should focus on current-context information only:

- session title
- branch tag
- bound server tag
- compact list / inspector visibility controls

### Composer Tightening

The composer should default to roughly a three-line editing height. It should still support normal
multi-line text entry, but the empty-state footprint must be much smaller than today.

The composer container styling should also be softened:

- lighter border or surface treatment
- smaller corner-radius emphasis if needed
- no heavy framed-box appearance

The intent is to preserve clarity without making the input area dominate the page.

### Audio Notice Compaction

The audio remediation notice should become a single-row compact bar. It should contain:

- concise alert label
- short actionable detail text
- one trailing remediation button

It should no longer consume a second line for title-plus-description unless a future action truly
requires expanded explanation.

## Architecture Notes

- Title-bar tab compaction belongs with the title-bar tab view implementation, not the workspace
  content tree.
- Chat layout width, collapse rails, session rows, and composer changes belong in the chat view
  module so the transaction stays localized to the chat surface.
- Audio notice compaction remains in the existing tools/downloads section, but should reuse the same
  compact-density principles as the updated chat workspace.
- Session-row action relocation should not introduce a second source of truth for export or fork
  behavior; the existing view-model actions remain the behavioral source of truth.

## Testing Strategy

- Swift view tests
  - title-bar tab control renders with the tighter compact style
  - chat layout renders narrower sidebar and inspector widths
  - collapsed side columns expose restore rails
  - selected chat-session row exposes compact session actions
  - workspace header no longer renders `Fork` and `Export`
  - composer renders with the tighter default height and lighter styling
  - audio setup notice renders as a single-row compact bar
- interaction tests
  - sidebar and inspector toggles collapse and restore the correct pane
  - session-row `Fork` and `Export` actions still dispatch the existing view-model operations

## Performance Probes

This is a desktop layout and interaction-density transaction. Runtime performance probes are `N/A`.

Delivery evidence should rely on:

- focused Swift regression tests
- changed-line coverage for touched Swift files
- visual verification in the running desktop app

## Scope Guardrails

- No redesign of non-chat tabs beyond the compact audio notice already requested
- No rewrite of chat transcript semantics or chat streaming behavior
- No new session-management capabilities beyond relocating existing actions
- No hidden overlay drawer system for the side panels
- No custom fake macOS window chrome
