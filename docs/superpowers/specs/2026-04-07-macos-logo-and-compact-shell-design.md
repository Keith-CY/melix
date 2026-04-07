# macOS Logo And Compact Shell Design

## Summary

Melix should adopt a repository-owned application logo and use it consistently across the desktop
workspace, the packaged Dock icon, and the menu bar tray icon. At the same time, the current
workspace chrome should be tightened into a shorter, denser shell bar that feels closer to a
native macOS utility window.

The approved direction is:

- use the provided Melix SVG as the repository source asset
- render a color application icon for the packaged Dock surface
- render a monochrome template icon for the tray surface
- show the Melix logo in the workspace header at the top-left
- replace the current two-layer header with a compact single-row shell bar
- keep the workspace tabs centered inside that shell bar
- remove the custom in-shell close action because macOS window chrome already owns close
- remove the current top-right `Refresh` toolbar action
- make the audio setup notice materially shorter
- prevent touched shell-bar and remediation buttons from wrapping their labels

## Problem

The current desktop surface has three issues:

1. It has no repository-owned application logo flow, so the packaged app does not expose the
   intended Melix identity in Dock or tray surfaces.
2. The workspace chrome is vertically heavy. It spends too much height on a title row and a second
   action row, while the operator wants a tighter utility-style shell.
3. The current controls are not fully native in tone. The shell includes a redundant close action,
   exposes a top-level refresh affordance that competes with content-local refresh actions, and
   allows longer action labels to wrap.

If Melix keeps the current shape, packaging will remain visually incomplete and the top of the
window will continue to feel bulkier than the actual operator tasks require.

## Approaches

### 1. Minimal logo-only patch

- Add a Dock icon and tray icon.
- Leave the current workspace shell layout mostly unchanged.

Pros:

- Smallest implementation.
- Low UI regression risk.

Cons:

- Does not address the user-approved compact shell-bar direction.
- Keeps the redundant refresh and close affordances in place.

Rejected.

### 2. Full native-branding and compact-shell refresh

- Add source and derived icon assets for page, Dock, and tray usage.
- Update the packaged app bundle to advertise an app icon and participate in Dock plus tray.
- Compress the workspace header into a single compact shell bar with centered tabs and a single
  icon-only command-center affordance.
- Tighten the audio setup notice and enforce one-line button labels.

Pros:

- Matches the approved product direction.
- Solves branding and shell-density problems together.
- Produces a coherent packaged-app story instead of a partial icon patch.

Cons:

- Touches both Swift UI and packaging code.
- Requires resource-pipeline decisions for template versus full-color icon assets.

Recommended.

### 3. Runtime-generated logo rendering only

- Keep only the SVG source and dynamically derive all app surfaces at runtime.

Pros:

- Appears to minimize committed assets.

Cons:

- Fragile for packaged macOS app icon flows.
- Still requires bundle-level icon support for Dock.
- Adds unnecessary runtime complexity to what should be a deterministic packaging surface.

Rejected.

## Recommended Design

### Logo Asset Model

Add the provided Melix SVG as the repository-owned source asset. From that source, commit derived
assets for the three required use cases:

- workspace branding asset
  - color-preserving
  - suitable for SwiftUI and AppKit view rendering
- Dock application icon asset
  - packaged in app-bundle resources
  - referenced from `Info.plist`
- tray template icon asset
  - monochrome template treatment for NSStatusItem usage
  - suitable for light and dark menu-bar appearances

The source SVG remains the design truth. Derived assets are committed so the packaged product does
not depend on runtime conversion.

### Workspace Shell Bar

Replace the current two-layer header region with one compact shell bar that contains:

- left cluster
  - Melix logo
  - short product label: `Melix`
- center cluster
  - `Chat`
  - `Image`
  - `Server`
  - `Tools`
  - `API`
- right cluster
  - one icon-only command-center entry point

This shell bar should be visibly shorter than the current top chrome and should feel like a native
utility strip rather than a web-style navigation header.

The current custom close action is removed. macOS window traffic-light controls already own close,
so Melix should not duplicate that command in the shell bar.

The current root toolbar `Refresh` action is also removed. Refresh remains valid only where it is
scoped to a specific content surface and still adds operator value.

### Audio Setup Notice

The current audio setup remediation surface in Tools should be rewritten as a short, low-height
single-row notice:

- condensed title
- shorter detail copy
- one remediation button on the trailing edge

The notice should remain clearly actionable, but it should stop consuming the height of a normal
card unless the content genuinely requires expansion later.

### Non-Wrapping Action Labels

Buttons touched by this transaction should keep their labels on a single line. This applies to:

- shell-bar controls
- compact audio-setup remediation action
- nearby dense controls that would visually degrade if they wrapped after the shell compaction

The goal is not to globally restyle every button in the product. The goal is to guarantee stable
compactness in the updated shell and adjacent remediation surfaces.

### Packaged App Behavior

The packaged Melix app should participate in both Dock and tray surfaces:

- Dock
  - visible with the packaged Melix app icon
- tray
  - visible with the Melix template icon

This is a product behavior change relative to a pure accessory-style menu-bar app. The packaged app
should no longer be treated as a tray-only product surface.

Development-time flows may still keep their current conveniences if needed, but the packaged-app
truth must be `Dock + tray`.

## Architecture Notes

- The menu bar renderer should own tray-icon assignment instead of relying on text-only status
  titles.
- The workspace header should remain in `DesktopWorkspaceShellView` so shell layout and tab
  placement stay co-located.
- Packaged icon behavior should be expressed through deterministic app-bundle resources and
  `Info.plist`, not through runtime best-effort conversion.
- The compact shell bar should not introduce a second command plane or duplicate native window
  management semantics.

## Testing Strategy

- Swift tests
  - shell-bar layout and interaction coverage
  - compact audio-setup notice rendering and remediation dispatch
  - status-menu renderer icon behavior
- Python packaging tests
  - app icon resources copied into the bundle
  - `Info.plist` references the packaged icon correctly
  - packaged app no longer advertises tray-only accessory semantics
- manual operator smoke
  - workspace logo visible in the header
  - tray icon visible and legible
  - packaged app icon visible in Dock

## Performance Probes

This is a branding, packaging, and desktop-layout transaction. Runtime performance probes are
`N/A`.

Delivery evidence should instead rely on:

- focused Swift and Python regression tests
- bundle resource inspection
- `Info.plist` inspection
- packaged-app visual smoke evidence

## Scope Guardrails

- No unrelated redesign of lower workspace content panes
- No global button-style rewrite across the whole product
- No attempt to remove all content-local refresh actions in this transaction
- No runtime SVG conversion dependency for packaged icons
- No duplicate in-shell close control once the compact shell bar ships
