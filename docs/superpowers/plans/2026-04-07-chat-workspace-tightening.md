# Chat Workspace Tightening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten the macOS chat workspace so the title-bar tabs fit cleanly, side panes waste less space, chat-specific actions live on the session row, the composer is smaller and lighter, and the audio notice becomes a compact single-row control.

**Architecture:** Keep the transaction localized to the existing macOS menu-bar app surface. Use small layout-metric constants and focused SwiftUI helper views inside the current chat and desktop shell modules so tests can assert compactness without introducing a separate design system. Reuse the existing `RuntimeViewModel` actions; this change is about ownership and layout, not new behavior.

**Tech Stack:** Swift 6, SwiftUI, AppKit-hosted SwiftUI tests, Swift Testing.

---

## Scope Notes

- This plan implements `docs/superpowers/specs/2026-04-07-chat-workspace-tightening-design.md`.
- This slice does not change chat streaming semantics, server-session behavior, or non-chat layout beyond the compact audio notice already approved.
- Runtime metrics for this scope are `N/A`; delivery evidence is focused Swift tests plus changed-line coverage.

## File Structure

- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopShellChromeView.swift`
  - Own the compact title-bar tab metrics and the visual density of the title-bar segmented control.
- `apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift`
  - Own chat sidebar width, inspector width, collapse rails, session-row action placement, workspace-header controls, composer sizing, and lighter composer styling.
- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
  - Own the compact single-row audio setup notice styling in the tools/downloads section.
- `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
  - Cover compact title-bar tabs, chat workspace compactness, side-rail rendering, relocated session actions, and compact audio notice rendering.
- `apps/macos-menubar/Tests/MenuBarTests/DesktopPolishSmokeTests.swift`
  - Keep smoke coverage green for the touched chat and downloads surfaces if helper coverage needs to move with the new views.

## Performance Probes And Success Metrics

- Runtime performance probes: `N/A`
- Delivery gates:
  - focused Swift view tests pass
  - changed-line coverage for touched Swift files is at least `95%`
  - visual smoke in the running app shows compact title-bar tabs, slimmer chat panes, rail-based collapse, relocated session menu actions, and a single-row audio notice

## Task 1: Tighten The Title-Bar Tabs

**Files:**
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopShellChromeView.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`

- [ ] **Step 1: Write the failing test**

Add a compactness-oriented test in `DesktopFoundationViewTests.swift` that hosts the title-bar tabs and asserts a constrained fitting height plus the presence of all five tab labels:

```swift
    @Test("title-bar tabs fit a compact height budget")
    @MainActor
    func titleBarTabsFitACompactHeightBudget() async throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await viewModel.start()

        let hosted = hostView(DesktopWorkspaceTitleBarTabsView(viewModel: viewModel))
        let renderedTexts = renderedTextValues(in: hosted)

        #expect(hosted.fittingSize.height <= DesktopShellChromeMetrics.titleBarTabHeightBudget)
        #expect(renderedTexts.contains("Chat"))
        #expect(renderedTexts.contains("Image"))
        #expect(renderedTexts.contains("Server"))
        #expect(renderedTexts.contains("Tools"))
        #expect(renderedTexts.contains("API"))
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'titleBarTabsFitACompactHeightBudget'
```

Expected: `FAIL` because `DesktopShellChromeMetrics` does not exist yet and the current rendered height is not constrained by an explicit compact budget.

- [ ] **Step 3: Write minimal implementation**

Add a small metrics type and tighten the tab strip spacing and padding in `DesktopShellChromeView.swift`:

```swift
enum DesktopShellChromeMetrics {
    static let titleBarTabHeightBudget: CGFloat = 30
    static let titleBarTabHorizontalPadding: CGFloat = 9
    static let titleBarTabVerticalPadding: CGFloat = 4
    static let titleBarTabContainerInset: CGFloat = 3
}

struct DesktopShellTabStripView: View {
    var body: some View {
        HStack(spacing: 3) {
            ForEach(DesktopSurface.allCases) { surface in
                Button {
                    selectSurface(surface)
                } label: {
                    Text(surface.rawValue)
                        .font(.caption.weight(selectedSurface == surface ? .semibold : .medium))
                        .lineLimit(1)
                        .padding(.horizontal, DesktopShellChromeMetrics.titleBarTabHorizontalPadding)
                        .padding(.vertical, DesktopShellChromeMetrics.titleBarTabVerticalPadding)
                        .background(...)
                }
                .buttonStyle(.plain)
                .fixedSize(horizontal: true, vertical: false)
            }
        }
        .padding(DesktopShellChromeMetrics.titleBarTabContainerInset)
        .background(...)
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'titleBarTabsFitACompactHeightBudget'
```

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add apps/macos-menubar/Sources/AppMain/Dashboard/DesktopShellChromeView.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift
git commit -m "fix(macos-menubar): tighten title bar tabs"
```

## Task 2: Compact The Chat Workspace And Move Session Actions

**Files:**
- Modify: `apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`

- [ ] **Step 1: Write the failing tests**

Add chat-layout tests that assert the compact metrics, rail rendering, and session-action relocation:

```swift
    @Test("chat workspace uses compact layout metrics")
    @MainActor
    func chatWorkspaceUsesCompactLayoutMetrics() {
        #expect(DesktopChatLayoutMetrics.sidebarIdealWidth <= 230)
        #expect(DesktopChatLayoutMetrics.inspectorIdealWidth <= 240)
        #expect(DesktopChatLayoutMetrics.composerMinHeight <= 84)
    }

    @Test("chat workspace hides header fork and export buttons")
    @MainActor
    func chatWorkspaceHidesHeaderForkAndExportButtons() async throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await viewModel.start()

        let hosted = hostView(
            DesktopChatSessionWorkspace(
                viewModel: viewModel,
                showsSidebar: .constant(true),
                showsInspector: .constant(true)
            )
        )
        let renderedTexts = renderedTextValues(in: hosted)

        #expect(renderedTexts.contains("Fork") == false)
        #expect(renderedTexts.contains("Export") == false)
    }

    @Test("chat collapsed rails render compact restore affordances")
    @MainActor
    func chatCollapsedRailsRenderCompactRestoreAffordances() {
        let leadingRail = hostView(DesktopChatPaneRail(edge: .leading, action: {}))
        let trailingRail = hostView(DesktopChatPaneRail(edge: .trailing, action: {}))

        #expect(leadingRail.fittingSize.width <= DesktopChatLayoutMetrics.collapsedRailWidth + 4)
        #expect(trailingRail.fittingSize.width <= DesktopChatLayoutMetrics.collapsedRailWidth + 4)
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'chatWorkspaceUsesCompactLayoutMetrics|chatWorkspaceHidesHeaderForkAndExportButtons|chatCollapsedRailsRenderCompactRestoreAffordances'
```

Expected: `FAIL` because the compact metrics and rail view do not exist yet, and the current workspace still renders `Fork` and `Export` in the header.

- [ ] **Step 3: Write minimal implementation**

Add compact chat metrics, slim restore rails, a tighter composer, and a session-row menu in `DesktopChatView.swift`:

```swift
enum DesktopChatLayoutMetrics {
    static let sidebarIdealWidth: CGFloat = 220
    static let inspectorIdealWidth: CGFloat = 232
    static let collapsedRailWidth: CGFloat = 28
    static let composerMinHeight: CGFloat = 76
}

private enum DesktopChatPaneRailEdge { case leading, trailing }

private struct DesktopChatPaneRail: View {
    let edge: DesktopChatPaneRailEdge
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: edge == .leading ? "sidebar.left" : "sidebar.right")
                .font(.caption.weight(.semibold))
                .frame(width: DesktopChatLayoutMetrics.collapsedRailWidth, maxHeight: .infinity)
        }
        .buttonStyle(.plain)
    }
}

private struct DesktopChatSessionRowActions: View {
    let fork: () -> Void
    let export: () -> Void

    var body: some View {
        Menu {
            Button("Fork", action: fork)
            Button("Export", action: export)
        } label: {
            Label("Session Actions", systemImage: "ellipsis.circle")
                .labelStyle(.iconOnly)
        }
        .menuStyle(.borderlessButton)
        .fixedSize(horizontal: true, vertical: false)
    }
}
```

Then wire them into `DesktopChatTabView`, `DesktopChatSessionSidebar`, and `DesktopChatSessionWorkspace`:

```swift
            if showsSidebar {
                DesktopChatSessionSidebar(viewModel: viewModel)
                    .frame(minWidth: 200, idealWidth: DesktopChatLayoutMetrics.sidebarIdealWidth)
            } else {
                DesktopChatPaneRail(edge: .leading) { showsSidebar = true }
            }

            ...

            if showsInspector {
                DesktopChatSessionInspector(viewModel: viewModel)
                    .frame(minWidth: 210, idealWidth: DesktopChatLayoutMetrics.inspectorIdealWidth)
            } else {
                DesktopChatPaneRail(edge: .trailing) { showsInspector = true }
            }
```

And reduce the composer weight:

```swift
                .frame(minHeight: DesktopChatLayoutMetrics.composerMinHeight)
                .padding(.horizontal, 10)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(Color(nsColor: .textBackgroundColor).opacity(0.75))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(Color.primary.opacity(0.08), lineWidth: 1)
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'chatWorkspaceUsesCompactLayoutMetrics|chatWorkspaceHidesHeaderForkAndExportButtons|chatCollapsedRailsRenderCompactRestoreAffordances|chat tab|chat session'
```

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift
git commit -m "fix(macos-menubar): compact chat workspace"
```

## Task 3: Compact The Audio Notice And Run Final Verification

**Files:**
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/DesktopPolishSmokeTests.swift`

- [ ] **Step 1: Write the failing test**

Extend the downloads-section coverage so the audio notice is asserted as a one-row compact treatment:

```swift
    @Test("downloads section renders audio setup notice as a compact single row")
    @MainActor
    func downloadsSectionRendersCompactAudioSetupNotice() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureSnapshot(makeAudioSetupSnapshot(models: [ModelCatalog.devTextModel(), ModelCatalog.mlxWhisperModel()]))
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let hosted = hostView(DesktopDownloadsToolSectionView(viewModel: viewModel))

        #expect(hosted.subviews.isEmpty == false)
        #expect(renderedTextValues(in: hosted).contains("Audio Setup Required"))
        #expect(renderedTextValues(in: hosted).contains("Install melix-audio-runtime-pack"))
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'downloadsSectionRendersCompactAudioSetupNotice|downloads section renders audio setup actions'
```

Expected: `FAIL` because the current notice still renders as a taller two-line treatment.

- [ ] **Step 3: Write minimal implementation**

Compress the existing audio setup row in `DesktopWorkspaceShellView.swift`:

```swift
                        HStack(spacing: 10) {
                            Label("Audio Setup Required", systemImage: "waveform.badge.exclamationmark")
                                .font(.caption.weight(.semibold))
                                .lineLimit(1)

                            Text("Install \(action.alias)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)

                            Spacer(minLength: 8)

                            Button(action.actionTitle) {
                                Task { await viewModel.performAudioSetupAction(action) }
                            }
                            .buttonStyle(.borderedProminent)
                            .controlSize(.small)
                            .fixedSize(horizontal: true, vertical: false)
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
```

- [ ] **Step 4: Run focused verification and coverage**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'titleBarTabsFitACompactHeightBudget|chatWorkspaceUsesCompactLayoutMetrics|chatWorkspaceHidesHeaderForkAndExportButtons|chatCollapsedRailsRenderCompactRestoreAffordances|downloadsSectionRendersCompactAudioSetupNotice|chat tab|chat session|downloads section renders audio setup actions'
python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopShellChromeView.swift apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopPolishSmokeTests.swift
git diff --check -- apps/macos-menubar/Sources/AppMain/Dashboard/DesktopShellChromeView.swift apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopPolishSmokeTests.swift
```

Expected:

- Swift tests: `PASS`
- changed-line coverage: `>= 95%`
- `git diff --check`: no output

- [ ] **Step 5: Commit**

```bash
git add apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopPolishSmokeTests.swift
git commit -m "fix(macos-menubar): compact audio notice"
```
