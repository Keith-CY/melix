# LoRA White Background Marketing Screenshot Alignment Round 6

## Context

The round 5 LoRA surface now follows the System Design Guide and the uploaded
design-system example at the information-architecture level, but the generated
screenshots still read too gray. The primary cause is that the LoRA visual
tokens use very low secondary-opacity fills over the default macOS window
background, and the screenshot renderer still captures an offscreen
`NSHostingView` rather than a real window-backed view.

The user specifically requested a pure visual pass:

- make the background white first
- optimize the UI from that white baseline
- produce website-suitable real-window screenshots

## Design Inputs

- `docs/design-system/README.md`
- `/Users/ChenYu/Downloads/Melix Design System.pdf`
- `/Users/ChenYu/Downloads/Melix Design System/ui_kits/macos-app/ToolsView.jsx`
- current LoRA screenshots under
  `artifacts/lora-marketing-screenshots/2026-04-24-polish/`

## Goals

1. Make LoRA Training and Diagnostics read on a white page background.
2. Keep the Digital Broadsheet principle: low structural color, clear ink,
   restrained interaction color.
3. Restore enough section, metric, selection, and chart contrast that static
   website screenshots no longer look washed out.
4. Replace the temporary offscreen screenshot capture with a window-backed
   renderer for the marketing screenshot test.
5. Keep business behavior unchanged.

## Non-Goals

- No new LoRA workflow behavior.
- No backend or protobuf changes.
- No broad redesign of Chat, Server, API, or Image.
- No permanent marketing asset pipeline beyond the current temporary screenshot
  renderer.

## Implementation Plan

### Slice 1: Visual Token Contract

Update focused view tests to lock the new white-background contract:

- LoRA page background is explicit white.
- section surface opacity is visible but still below typical card chrome.
- metric surface opacity is slightly stronger than before.
- selected history and chart fills have enough contrast for exported PNGs.

### Slice 2: LoRA Surface Background

Apply the white background to the Tools workspace when the selected section is
Training or Diagnostics. Keep the rest of the app on the existing macOS window
background unless that surface is explicitly updated in a future pass.

### Slice 3: Section And Result Contrast

Retune `DesktopLoRAVisualPolish` values and reuse them consistently for:

- editorial section cards
- metric cards
- selected history rows
- chart fills
- expandable secondary settings

The pass should keep borders light and avoid large gray slabs.

### Slice 4: Window-Backed Screenshot Capture

Update `TempLoRAScreenshotTests` so marketing screenshots render through an
`NSWindow` with a white background and capture the window-backed content.
The helper may fall back to view caching only if the platform window capture is
unavailable, but the default mode must be window-backed.

## Tests And Verification

Focused red/green checks:

```bash
swift test --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests/loraVisualPolishTokensUseWhiteMarketingBackground'
swift test --package-path apps/macos-menubar --filter 'TempLoRAScreenshotTests/loraMarketingScreenshotRendererUsesWindowBackedWhiteCanvas'
```

Full verification:

```bash
swift test --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests|RuntimeViewModelTests|Phase8LoRAWindowSmokeTests|TempLoRAScreenshotTests'
swift test --enable-code-coverage --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests|RuntimeViewModelTests|Phase8LoRAWindowSmokeTests|TempLoRAScreenshotTests'
python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/TempLoRAScreenshotTests.swift
python3 scripts/m15_desktop_polish_smoke.py --json
```

Screenshot verification:

- refresh `artifacts/lora-marketing-screenshots/2026-04-24-polish/`
- inspect at least:
  - `01-tools-training-overview.png`
  - `04-diagnostics-benchmark.png`
  - `05-diagnostics-matrix.png`

## Metrics

- changed-line Swift coverage for touched source/test files: at least 95%
- smoke `presentation_lag_ms`
- smoke `presentation_flush_count`
- smoke operator session restore/write latency
