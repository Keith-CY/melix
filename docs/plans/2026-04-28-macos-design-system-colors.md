# macOS Design System Colors Implementation Plan

## Goal

Align the native macOS operator app colors with `docs/design-system/README.md`
and `docs/design-system/colors_and_type.css`.

## Design Inputs

- `docs/design-system/README.md`
- `docs/design-system/colors_and_type.css`
- `apps/macos-menubar/Sources/AppMain/Branding/MelixDesignTokens.swift`

## Scope

- Keep the change inside the macOS menu bar app surface.
- Make the design-system teal `#0F766E` the fixed interaction accent in app
  code instead of the user-configurable macOS system accent color.
- Preserve the design-system dark-mode foreground and background overrides in
  the native token model.
- Add explicit SwiftUI tokens for design-system status colors and chat bubble
  base hues.
- Replace direct `Color.accentColor`, `.green`, `.orange`, `.red`, and `.blue`
  usages in the touched UI surfaces where they represent Melix design-system
  semantics.
- Keep layout, typography, behavior, and runtime code unchanged.

## Implementation Steps

1. Add failing tests in
   `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
   that assert the design-system RGB values and opacities exposed by
   `MelixDesignTokens`.
2. Run the targeted macOS test suite and confirm the new test fails before
   production code changes.
3. Update
   `apps/macos-menubar/Sources/AppMain/Branding/MelixDesignTokens.swift` with
   explicit light/dark sRGB color specs, fixed accent color, exact status
   colors, and exact chat bubble opacities from `colors_and_type.css`.
4. Replace direct app accent and status color references in the macOS app
   sources with the new tokens.
5. Run the targeted macOS tests, then the relevant repository command
   `make swift-test` if the targeted suite passes.

## Metrics

- Runtime performance probes: N/A. This change only adjusts static UI color
  tokens and SwiftUI color references.
- Automated coverage target: covered by macOS menu bar unit tests for the
  changed token surface. Full changed-scope coverage measurement is N/A unless
  the existing macOS coverage tooling is available in this worktree.
