# LoRA System Design Alignment Round 5

## Summary

Realign the macOS LoRA workflow with the repository design system and the
uploaded operator UI examples so the LoRA business surfaces read like Melix's
editorial operator tooling instead of a sequence of configuration slabs.

This round focuses on information architecture and surface hierarchy rather
than new backend behavior.

## Design Inputs

- `docs/design-system/README.md`
- `docs/plans/2026-04-24-lora-visual-polish-round-4.md`
- `"/Users/ChenYu/Downloads/Melix Design System/ui_kits/macos-app/ToolsView.jsx"`
- `"/Users/ChenYu/Downloads/Melix Design System/ui_kits/macos-app/ServerView.jsx"`
- uploaded PDF reference: `Melix Design System.pdf`

## Problems To Solve

### 1. The LoRA page still starts like a workspace editor

The current Training surface exposes `Workflow Status`, `Workflow Actions`,
`Selected Configuration`, and `Training Configuration` as separate first-class
cards. That is correct functionally, but it does not match the operator mockup
language, which begins with a primary business summary and a compact action row.

### 2. Adapter and job information is split too mechanically

`Adapter Activation`, `Saved Adapters`, and `Training Jobs` force the user to
walk the workflow model instead of scanning the business state. The mockup
prefers `Adapter Registry` and `Training History`, which are easier to read as
operational inventory.

### 3. Diagnostics titles and sequencing do not read like reports

`Benchmark Snapshot`, `Benchmark Results`, and `Benchmark History` are
technically explicit, but the example surfaces present benchmark output more as
a report artifact with controls around it. The LoRA diagnostics surface should
use report-first language and grouping.

## Scope

### In

- `Tools > Training` layout and section hierarchy
- `Tools > Diagnostics` benchmark / matrix / evaluation section titles and
  grouping
- focused screenshot refresh for the LoRA marketing artifact set
- focused SwiftUI tests covering the new hierarchy

### Out

- runtime, protocol, or persistence changes
- new LoRA workflow actions or backend semantics
- non-LoRA app surfaces

## Target Surface Model

### Training

The Training surface should read top-down as:

1. `Primary Model`
2. `Workflow Snapshot`
3. `Run Draft`
4. `Adapter Registry`
5. `Experiment Groups`
6. `Training History`

The first two sections carry the page's operator context. Configuration editing
is still available, but it becomes secondary to the business state.

### Diagnostics

The Diagnostics surface should read top-down as:

1. `Diagnostics Actions`
2. stage-specific report card:
   - `Bench Report`
   - `Matrix Report`
   - `Evaluation Report`
3. stage-specific configuration
4. stage-specific history
5. secondary notes (`Model Info`, `Doctor Report`, `Runtime Metrics Snapshot`)

This keeps the report artifact ahead of the controls and history.

## Implementation Plan

### Slice 1 — Hierarchy tests

- add failing view tests for the new Training and Diagnostics section titles
- assert the older card names that no longer match the guide are absent

### Slice 2 — Training realignment

- merge the base-model summary and action row into `Primary Model`
- merge status and selected config into `Workflow Snapshot`
- rename `Training Configuration` to `Run Draft`
- merge activation and saved adapter inventory into `Adapter Registry`
- rename `Training Jobs` to `Training History`

### Slice 3 — Diagnostics report-first naming

- rename stage snapshot cards to report-oriented titles
- keep the existing result-first behavior, but make the nomenclature match the
  operator mockup language

### Slice 4 — Screenshot refresh

- refresh the temporary screenshot renderer outputs so the exported images match
  the new hierarchy

## Files Expected

- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- `apps/macos-menubar/Tests/MenuBarTests/TempLoRAScreenshotTests.swift`
- `docs/plans/2026-04-24-lora-system-design-alignment-round-5.md`

## Verification

```bash
swift test --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests|RuntimeViewModelTests|Phase8LoRAWindowSmokeTests|TempLoRAScreenshotTests'
swift test --enable-code-coverage --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests|RuntimeViewModelTests|Phase8LoRAWindowSmokeTests|TempLoRAScreenshotTests'
python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/TempLoRAScreenshotTests.swift
python3 scripts/m15_desktop_polish_smoke.py --json
```

## Success Criteria

- the LoRA Training first viewport now starts with business context, not only
  configuration UI
- adapter and history sections use operator language from the system design
  example
- diagnostics report cards read like report artifacts instead of generic
  snapshots
- changed-line automated coverage remains at or above 95 percent for touched
  executable lines

## Metrics

- changed-line automated coverage >= 95%
- runtime metrics: `N/A` unless the implementation unexpectedly touches runtime
  behavior
