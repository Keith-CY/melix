# Window UI And Menubar UI Optimization Implementation Plan

> **For agentic workers:** Implement this plan task-by-task and keep the checkboxes current as
> verification evidence changes.

**Goal:** Improve the native Melix Window UI and Menubar UI through shared window chrome,
state-first operator triage, and clearer Tools workflows without changing backend ownership or
protocol contracts.

**Architecture:** Keep the macOS app as an operator shell over `RuntimeViewModel` and the existing
CLI/control-plane boundaries. Add app-local UI composition types for shared pane chrome, state
priority, menu recovery actions, and Tools categorization. Preserve the existing write-path
semantics and route workflow actions through the current app/client/CLI bridge APIs.

**Tech Stack:** SwiftUI, AppKit `NSMenu`, Swift Testing, existing Melix menu bar smoke scripts.

---

## Scope

- [x] Low-risk polish: shared split workspace chrome, icon-only pane controls, keyboard shortcuts,
  accessibility labels, and visual-quality smoke coverage.
- [x] State-first redesign: Command Center and Menubar expose runtime health, recovery actions,
  active workflow signals, and latest errors before lower-priority informational notices.
- [x] Tools workflow redesign: group Tools into Models, Build, Validate, and System categories;
  fold advanced fields behind disclosure groups; keep primary task fields visible.

## Non-Goals

- [x] No protobuf schema changes.
- [x] No generated protocol artifact changes.
- [x] No control-plane, worker, or model-operation behavior changes.
- [x] No second orchestration engine inside the app.

## Verification

Targeted checks:

```bash
swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests
swift test --package-path apps/macos-menubar --filter StatusMenuTests
swift test --package-path apps/macos-menubar --filter DesktopPolishSmokeTests
python3 scripts/m15_desktop_polish_smoke.py --json
```

Broader handoff checks, when time and environment permit:

```bash
make swift-test
make py-test
make integration-test
```

Metrics report:

- Runtime performance probes: `N/A` for pure UI layout changes.
- UI evidence: targeted Swift tests, desktop polish smoke JSON, and Window UI render/smoke tests for
  compact and wide sizes.

Executed verification:

- `xcrun swift test --package-path apps/macos-menubar --filter Phase8LoRAWindowSmokeTests`: passed.
- `xcrun swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests`: passed, 105 tests.
- `xcrun swift test --package-path apps/macos-menubar --filter "StatusMenuTests|DesktopPolishSmokeTests"`: passed, 23 tests.
- `python3 scripts/m15_desktop_polish_smoke.py --json`: passed with `ok: true`,
  `grounded_surface_count: 5`, `grounded_tool_section_count: 6`,
  `top_banner_title: "Download Recovery Available"`, `presentation_lag_ms: 205.667`.
- `make swift-test`: passed.
- `make py-test`: passed, 821 tests.
- `make integration-test`: passed, 85 tests, 1 skipped.

Integration helper note:

- Phase 8 CLI/window integration build helpers now use the repository's scoped `xcrun swift`
  command and scratch-path isolation to avoid mixing local `swift` and `xcrun swift` toolchains.

## Acceptance Criteria

- [x] The five top-level Window UI surfaces render with shared pane chrome and no in-content shell
  regression.
- [x] Icon-only actions have help and accessibility labels.
- [x] Keyboard shortcuts cover surface navigation, Command Center, primary run/send actions, and
  sidebar/inspector toggles where a surface supports them.
- [x] Menubar content prioritizes recovery/error/runtime state ahead of model actions and general
  console access.
- [x] Command Center shows global runtime health, primary model, queue/download recovery, active
  workflow, and latest error summaries.
- [x] Tools sections are grouped by Models, Build, Validate, and System while preserving all
  existing underlying actions.
- [x] Training, Server defaults, and Image defaults expose primary fields first and advanced fields
  behind disclosure groups.
