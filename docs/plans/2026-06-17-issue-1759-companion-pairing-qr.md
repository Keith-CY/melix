# Issue 1759 Companion Pairing QR

## Goal

Render a local-only QR preview for the existing `melix-companion:` pairing code
inside the desktop Authentication companion pairing panel.

## Best End-State Architecture

Companion QR rendering stays desktop-local and derives exclusively from the
already transient `melix-companion:` code. The gateway authorization model does
not change: companion tokens remain `companion_read_only`, revocable, and scoped
to existing read-only routes. The QR image is a presentation of bearer material,
not a new persisted credential.

The desktop app should generate the QR image with macOS system frameworks
(`CoreImage` plus `AppKit`) so the slice does not add dependencies or protocol
surface. QR rendering belongs to the AppMain UI layer because it is a local
operator transfer affordance, while `RuntimeViewModel` remains responsible only
for producing the canonical pairing bundle and compact code.

## Slice Boundary

Included:

- add a small QR generator for non-empty pairing-code strings;
- render a bounded QR preview in the active companion pairing panel;
- keep the existing narrow 360 px panel smoke guard;
- document QR handling as secret bearer material;
- focused Swift tests for QR generation, disabled empty input, source wiring,
  and narrow panel hosting.

Excluded:

- mobile/PWA import of `melix-companion:` codes;
- real browser companion status-page smoke;
- changing gateway read-only routes, redaction, token scope, or token lifetime.

## Performance Probes and Metrics

- Runtime metrics: no new gateway call or polling path is introduced.
- QR rendering is on-demand SwiftUI/AppKit presentation over the currently active
  compact code. The code string is small relative to the companion bundle and is
  only rendered in the Authentication panel.
- Merge gate: scoped performance report must remain `Status: ok` with zero
  regressions.

## Implementation Plan

1. Add failing menu-bar tests proving `CompanionPairingQRCode.image(for:)`
   returns an image for a non-empty `melix-companion:` code and returns `nil`
   for blank input.
2. Add a source-level UI assertion that the Authentication companion pairing
   surface contains a QR preview label and QR image generator wiring.
3. Extend the active companion panel test to keep the 360 px host guard with the
   QR preview present.
4. Implement `CompanionPairingQRCode` with `CIFilter.qrCodeGenerator`, scaled
   nearest-neighbor output, and an `NSImage`.
5. Render the QR image only when `viewModel.companionPairingCodeText()` returns
   a value, with bounded dimensions and help text warning that it contains the
   read-only bearer token.
6. Update `docs/runbooks/persistent-sessions.md` to describe QR transfer and the
   same secret-handling boundary as the copied bundle/code.

## Verification

Focused Swift tests:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" xcrun swift test --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests/(companionPairingQRCodeGeneratesOnlyForActiveCodes|apiAuthenticationSurfaceIncludesCompanionPairingTokenControls|companionPairingPanelRendersIdleActiveAndFailureStates)'
```

Changed-line coverage:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" xcrun swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'DesktopFoundationViewTests/(companionPairingQRCodeGeneratesOnlyForActiveCodes|apiAuthenticationSurfaceIncludesCompanionPairingTokenControls|companionPairingPanelRendersIdleActiveAndFailureStates)'
uv run --python 3.12 python scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift
```

Full gate before PR:

```bash
make swift-test
make py-test
make integration-test
```

## Deferred Work

- Companion mobile/PWA import flow for `melix-companion:` QR/code payloads.
- Real browser companion status-page smoke in a narrow viewport.
