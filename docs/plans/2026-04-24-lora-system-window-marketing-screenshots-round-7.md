# LoRA System Window Marketing Screenshots Round 7

## Context

Round 6 made the LoRA marketing screenshots white-background and window-backed,
but the exported PNGs are still content captures. They do not include the real
macOS window frame, title bar, or shadow that the user wants for website
promotion.

This round adds a second screenshot output path instead of replacing the clean
content screenshots.

## Goals

1. Keep the existing white content screenshots unchanged.
2. Add system-level window screenshots under a dedicated `window/` artifact
   directory.
3. Capture the actual macOS `NSWindow` frame and shadow with a titled window.
4. Keep the captured app content white and visually aligned with the System
   Design Guide.
5. Make the screenshot helper testable and stable in SwiftPM test runs.

## Non-Goals

- No app behavior changes.
- No LoRA workflow changes.
- No live backend or Computer Use dependency.
- No replacement of the existing content-only marketing screenshots.

## Implementation Plan

### Slice 1: System Window Capture Contract

Add a focused screenshot test that writes a small system-window PNG and verifies:

- the configured system capture mode is explicit
- the file exists and decodes
- captured dimensions are larger than the content dimensions, proving the frame
  and/or shadow were included

### Slice 2: Window Capture Helper

Add a helper that:

- creates a titled `NSWindow`
- installs an `NSHostingView` with the white screenshot canvas
- orders the window onscreen long enough for AppKit to materialize it
- captures the window via `screencapture -l <windowID>` so the implementation
  works with the macOS 15 SDK where `CGWindowListCreateImage` is unavailable
- writes the captured `CGImage` as PNG
- retains the window through the test process to avoid SwiftUI/AppKit teardown
  crashes seen in round 6

### Slice 3: Framed LoRA Artifacts

Update `TempLoRAScreenshotTests` to additionally write:

- `window/01-tools-training-overview-window.png`
- `window/04-diagnostics-benchmark-window.png`
- `window/05-diagnostics-matrix-window.png`

These are the website-promotion candidates with real macOS frame/shadow.

## Verification

```bash
swift test --package-path apps/macos-menubar --filter 'TempLoRAScreenshotTests/loraMarketingScreenshotRendererWritesSystemWindowFrame'
swift test --package-path apps/macos-menubar --filter TempLoRAScreenshotTests
swift test --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests|RuntimeViewModelTests|Phase8LoRAWindowSmokeTests|TempLoRAScreenshotTests'
swift test --enable-code-coverage --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests|RuntimeViewModelTests|Phase8LoRAWindowSmokeTests|TempLoRAScreenshotTests'
python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift apps/macos-menubar/Tests/MenuBarTests/TempLoRAScreenshotTests.swift
python3 scripts/m15_desktop_polish_smoke.py --json
```
