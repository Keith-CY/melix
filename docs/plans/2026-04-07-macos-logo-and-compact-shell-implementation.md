# macOS Logo And Compact Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship repository-owned Melix branding across the workspace header, packaged Dock icon, and tray icon while replacing the current two-row desktop chrome with a tighter single-row shell bar and a denser audio setup notice.

**Architecture:** Keep shell composition anchored in `DesktopWorkspaceShellView`, but extract the compact shell chrome into focused helpers so the huge workspace file does not grow further. Introduce a small branding resource layer in the Swift package, add an explicit menu-bar presentation contract so packaged builds can run in `Dock + tray`, and wire bundle resources deterministically from the packaging scripts instead of doing runtime asset conversion.

**Tech Stack:** Swift Package Manager resources, SwiftUI/AppKit, Python packaging helpers, Swift Testing, pytest, repository changed-line coverage scripts.

---

## Scope

- [ ] Commit the provided SVG as the repository source asset and add deterministic derived assets for workspace, tray, and Dock usage.
- [ ] Show the Melix logo at the top-left of the workspace shell.
- [ ] Replace the existing two-row shell header with one compact row containing left brand, centered tabs, and one icon-only command-center action.
- [ ] Remove the custom in-shell close action and the root-level `Refresh` toolbar action.
- [ ] Rewrite the Tools audio setup remediation into a shorter single-row notice with non-wrapping action labels.
- [ ] Make the packaged app launch in `Dock + tray`, keep development-time behavior explicitly configurable, and package the app icon into `Info.plist`.

## Probes And Success Metrics

- [ ] Branding probe:
  - Swift package resources resolve the workspace logo and tray template asset through a single branding helper.
- [ ] Presentation probe:
  - `MenuBarBootstrapEnvironment` parses a presentation mode environment contract and packaged launches resolve to `.dockAndTray`.
- [ ] Tray probe:
  - `StatusMenu` renders a template image on the `NSStatusItem` button and exposes the runtime title through tooltip/accessibility text instead of text-only chrome.
- [ ] Workspace chrome probe:
  - the shell renders `Melix`, `Chat`, `Image`, `Server`, `Tools`, `API`, and the compact audio setup action in one-line controls, and root `Refresh` is absent.
- [ ] Packaging probe:
  - the unsigned bundle copies the app icon into `Contents/Resources`, writes `CFBundleIconFile`, and no longer writes tray-only `LSUIElement = true`.
- [ ] Coverage probe:
  - changed-line coverage for the touched handwritten Swift and Python scope is at least `95%`.

## File Structure

- `apps/macos-menubar/Package.swift`
  - add processed SwiftPM resources for branded assets.
- `apps/macos-menubar/Sources/AppMain/Branding/MelixBranding.swift`
  - central resource loader for workspace logo, tray template icon, and shell constants.
- `apps/macos-menubar/Sources/AppMain/Resources/Branding/melix_logo.svg`
  - repository-owned source asset copied from the provided operator file.
- `apps/macos-menubar/Sources/AppMain/Resources/Branding/melix-logo-workspace.png`
  - color workspace logo used in SwiftUI/AppKit.
- `apps/macos-menubar/Sources/AppMain/Resources/Branding/melix-status-template.png`
  - monochrome tray template asset loaded by `NSStatusItem`.
- `apps/macos-menubar/Sources/AppMain/Resources/Branding/MelixAppIcon.icns`
  - packaged Dock icon copied into the macOS bundle.
- `apps/macos-menubar/Sources/AppMain/AppMain.swift`
  - presentation-mode contract and activation-policy wiring.
- `apps/macos-menubar/Sources/AppMain/MenuBar/StatusMenu.swift`
  - tray image rendering and tooltip/title behavior.
- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopShellChromeView.swift`
  - compact shell bar, brand cluster, centered tabs, and icon-only command-center affordance.
- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
  - replace the old two-row shell composition and tighten the audio setup notice/button layout.
- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`
  - remove the root toolbar refresh action.
- `apps/macos-menubar/Tests/MenuBarTests/AppMainBootstrapTests.swift`
  - presentation mode and activation-policy tests.
- `apps/macos-menubar/Tests/MenuBarTests/StatusMenuTests.swift`
  - tray image and tooltip rendering tests.
- `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
  - compact shell/header rendering and audio notice tests.
- `services/mlx-worker-python/worker/productization/macos_app_bundle.py`
  - bundle icon layout, `Info.plist` contract, and packaged launch environment defaults.
- `scripts/package_macos_menubar_app.py`
  - package-script argument forwarding for icon-aware bundle creation.
- `services/mlx-worker-python/tests/test_macos_app_bundle.py`
  - bundle icon and Dock/tray presentation tests.
- `services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py`
  - packaging entrypoint argument forwarding tests.
- `docs/runbooks/platform-packaging-targets.md`
  - document the new Dock + tray packaged behavior and app icon resource contract.

## Implementation Tasks

### Task 1: Branding Resources And Presentation Mode Contract

**Files:**
- Create: `apps/macos-menubar/Sources/AppMain/Branding/MelixBranding.swift`
- Create: `apps/macos-menubar/Sources/AppMain/Resources/Branding/melix_logo.svg`
- Create: `apps/macos-menubar/Sources/AppMain/Resources/Branding/melix-logo-workspace.png`
- Create: `apps/macos-menubar/Sources/AppMain/Resources/Branding/melix-status-template.png`
- Create: `apps/macos-menubar/Sources/AppMain/Resources/Branding/MelixAppIcon.icns`
- Modify: `apps/macos-menubar/Package.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/AppMain.swift`
- Test: `apps/macos-menubar/Tests/MenuBarTests/AppMainBootstrapTests.swift`

- [ ] **Step 1: Write the failing Swift tests for presentation-mode parsing and activation-policy selection**

```swift
@Test("bootstrap environment defaults packaged presentation to tray only unless overridden")
@MainActor
func bootstrapEnvironmentDefaultsPresentationMode() {
    let environment = MenuBarBootstrapEnvironment(environment: [:])
    #expect(environment.presentationMode == .tray)
}

@Test("bootstrap environment honors dock and tray presentation override")
@MainActor
func bootstrapEnvironmentHonorsDockAndTrayPresentationMode() {
    let environment = MenuBarBootstrapEnvironment(
        environment: ["MELIX_MENU_BAR_PRESENTATION_MODE": "dock-and-tray"]
    )
    #expect(environment.presentationMode == .dockAndTray)
}

@Test("launcher uses regular activation policy for dock and tray presentation")
@MainActor
func launcherUsesRegularActivationPolicyForDockAndTray() async throws {
    let app = RecordingApplicationLifecycle()
    let bootstrap = MelixMenuBarBootstrap(client: FakeControlPlaneXPCClient())

    MelixMenuBarLauncher.launch(
        application: app,
        presentationMode: .dockAndTray,
        bootstrapFactory: { bootstrap },
        retain: { _ in }
    )

    #expect(app.recordedPresentationModes == [.dockAndTray])
}
```

- [ ] **Step 2: Run the targeted Swift tests to confirm the new contract is not implemented yet**

Run: `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter AppMainBootstrapTests`

Expected: FAIL with unknown `presentationMode` members or missing launcher overloads.

- [ ] **Step 3: Add the resource pipeline and branding helper**

```swift
.executableTarget(
    name: "AppMain",
    dependencies: [...],
    path: "Sources/AppMain",
    resources: [
        .process("Resources"),
    ]
)
```

```swift
enum MelixBranding {
    static let productName = "Melix"
    static let workspaceLogoResource = "melix-logo-workspace"
    static let trayTemplateResource = "melix-status-template"
    static let appIconFile = "MelixAppIcon.icns"

    static func workspaceLogo() -> NSImage {
        loadImage(named: workspaceLogoResource)
    }

    static func trayTemplateIcon() -> NSImage {
        let image = loadImage(named: trayTemplateResource)
        image.isTemplate = true
        return image
    }
}
```

- [ ] **Step 4: Add the presentation-mode model and use it in the launcher**

```swift
public enum MenuBarPresentationMode: String, Equatable {
    case tray
    case dockAndTray = "dock-and-tray"

    var activationPolicy: NSApplication.ActivationPolicy {
        switch self {
        case .tray:
            return .accessory
        case .dockAndTray:
            return .regular
        }
    }
}

struct MenuBarBootstrapEnvironment {
    let presentationMode: MenuBarPresentationMode

    init(environment: [String: String]) {
        presentationMode = MenuBarPresentationMode(
            environmentValue: environment["MELIX_MENU_BAR_PRESENTATION_MODE"]
        )
        ...
    }
}
```

```swift
public protocol MenuBarApplicationLifecycle {
    func setActivationPolicy(_ activationPolicy: NSApplication.ActivationPolicy)
    func run()
}

MelixMenuBarLauncher.launch(
    application: application,
    presentationMode: environment.presentationMode,
    bootstrapFactory: bootstrapFactory,
    retain: retain
)
```

- [ ] **Step 5: Re-run the targeted Swift tests**

Run: `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter AppMainBootstrapTests`

Expected: PASS for the new presentation-mode coverage and existing startup-surface cases.

- [ ] **Step 6: Commit the branding foundation slice**

```bash
git add apps/macos-menubar/Package.swift \
  apps/macos-menubar/Sources/AppMain/Branding/MelixBranding.swift \
  apps/macos-menubar/Sources/AppMain/Resources/Branding \
  apps/macos-menubar/Sources/AppMain/AppMain.swift \
  apps/macos-menubar/Tests/MenuBarTests/AppMainBootstrapTests.swift
git commit -m "feat: add melix branding resources and presentation modes"
```

### Task 2: Tray Icon Rendering And Compact Shell Chrome

**Files:**
- Modify: `apps/macos-menubar/Sources/AppMain/MenuBar/StatusMenu.swift`
- Create: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopShellChromeView.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`
- Test: `apps/macos-menubar/Tests/MenuBarTests/StatusMenuTests.swift`
- Test: `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`

- [ ] **Step 1: Write the failing Swift tests for tray image rendering and compact shell content**

```swift
@Test("AppKit renderer assigns the tray template icon and tooltip")
@MainActor
func appKitRendererAssignsTemplateIconAndTooltip() async throws {
    guard !MenuBarTestEnvironment.isHeadlessCI else { return }
    let renderer = AppKitStatusMenuRenderer(statusBar: .system)
    let target = NSObject()
    renderer.render(
        content: StatusMenuContent(title: "Melix Ready", items: [.action("Quit Melix", .quit)]),
        target: target,
        action: #selector(getter: NSObject.description)
    )

    let button = try #require(renderer.currentStatusItem.button)
    #expect(button.image != nil)
    #expect(button.image?.isTemplate == true)
    #expect(button.toolTip == "Melix Ready")
}
```

```swift
@Test("workspace shell renders compact branded chrome and compact audio setup notice")
@MainActor
func workspaceShellRendersCompactBrandedChrome() async throws {
    let client = FakeControlPlaneXPCClient()
    let viewModel = RuntimeViewModel(client: client)
    await viewModel.start()

    let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
    let values = renderedTextValues(in: view)

    #expect(values.contains("Melix"))
    #expect(values.contains("Chat"))
    #expect(values.contains("Image"))
    #expect(values.contains("Server"))
    #expect(values.contains("Tools"))
    #expect(values.contains("API"))
    #expect(values.contains("Audio Setup Required"))
    #expect(values.contains("Refresh") == false)
}
```

- [ ] **Step 2: Run the targeted Swift tests to capture the current failures**

Run: `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter StatusMenuTests --filter DesktopFoundationViewTests`

Expected: FAIL because the renderer is text-only and the shell still renders the old two-row layout with root refresh.

- [ ] **Step 3: Implement tray icon rendering**

```swift
public func render(content: StatusMenuContent, target: AnyObject, action: Selector) {
    let button = statusItem.button
    button?.title = ""
    button?.image = MelixBranding.trayTemplateIcon()
    button?.toolTip = content.title
    button?.imagePosition = .imageOnly
    statusItem.menu = Self.makeMenu(content: content, target: target, action: action)
}
```

- [ ] **Step 4: Replace the header stack with a compact single-row shell bar**

```swift
VStack(spacing: 0) {
    if let banner = viewModel.desktopBannerState {
        DesktopShellBannerView(...)
    }

    DesktopShellChromeView(viewModel: viewModel)
        .padding(.horizontal, 18)
        .padding(.top, 12)
        .padding(.bottom, 10)

    Divider()

    shellContent
}
```

```swift
struct DesktopShellChromeView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        HStack(spacing: 16) {
            DesktopShellBrandView()
            Spacer(minLength: 16)
            DesktopShellTabStripView(...)
            Spacer(minLength: 16)
            Button(action: viewModel.openCommandCenter) {
                Image(systemName: "command.circle")
            }
            .buttonStyle(.borderless)
        }
    }
}
```

- [ ] **Step 5: Tighten the audio setup notice and remove the root toolbar refresh**

```swift
if viewModel.audioSetupActions.isEmpty == false {
    VStack(spacing: 8) {
        ForEach(viewModel.audioSetupActions) { action in
            HStack(spacing: 10) {
                Label("Audio Setup Required", systemImage: "waveform.badge.exclamationmark")
                    .font(.subheadline.weight(.semibold))
                Text(action.alias)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Button(action.actionTitle) { ... }
                    .fixedSize()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
        }
    }
}
```

```swift
public var body: some View {
    DesktopWorkspaceShellView(viewModel: viewModel)
        .frame(minWidth: 980, minHeight: 680)
}
```

- [ ] **Step 6: Re-run the targeted Swift tests**

Run: `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter StatusMenuTests --filter DesktopFoundationViewTests`

Expected: PASS for tray icon rendering, compact shell texts, and the shorter audio setup notice.

- [ ] **Step 7: Commit the desktop chrome slice**

```bash
git add apps/macos-menubar/Sources/AppMain/MenuBar/StatusMenu.swift \
  apps/macos-menubar/Sources/AppMain/Dashboard/DesktopShellChromeView.swift \
  apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift \
  apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift \
  apps/macos-menubar/Tests/MenuBarTests/StatusMenuTests.swift \
  apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift
git commit -m "feat: compact desktop shell chrome and tray icon"
```

### Task 3: Packaging Bundle Icon And Dock + Tray Behavior

**Files:**
- Modify: `services/mlx-worker-python/worker/productization/macos_app_bundle.py`
- Modify: `scripts/package_macos_menubar_app.py`
- Modify: `services/mlx-worker-python/tests/test_macos_app_bundle.py`
- Modify: `services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py`
- Modify: `docs/runbooks/platform-packaging-targets.md`

- [ ] **Step 1: Write the failing Python tests for icon copying and Dock-visible packaged behavior**

```python
def test_render_info_plist_sets_bundle_icon_and_dock_visible_defaults() -> None:
    payload = plistlib.loads(
        render_info_plist(
            app_name="Melix",
            bundle_id="io.melix.menubar.preview",
            version="0.1.0",
            icon_file="MelixAppIcon.icns",
        )
    )

    assert payload["CFBundleIconFile"] == "MelixAppIcon.icns"
    assert "LSUIElement" not in payload
```

```python
def test_write_unsigned_macos_app_bundle_copies_app_icon_and_packaged_presentation_env(tmp_path: Path) -> None:
    ...
    manifest = write_unsigned_macos_app_bundle(..., icon_source_path=icon_file)
    plist_payload = plistlib.loads(Path(manifest["plist_path"]).read_bytes())
    launcher = Path(manifest["launcher_path"]).read_text(encoding="utf-8")

    assert Path(manifest["resources_path"]).joinpath("MelixAppIcon.icns").exists()
    assert plist_payload["CFBundleIconFile"] == "MelixAppIcon.icns"
    assert 'export MELIX_MENU_BAR_PRESENTATION_MODE="dock-and-tray"' in launcher
```

- [ ] **Step 2: Run the targeted Python tests to verify the current bundle contract fails**

Run: `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_macos_app_bundle.py services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py -q`

Expected: FAIL because `render_info_plist()` still writes `LSUIElement`, no icon file is copied, and the package script does not forward icon-aware arguments.

- [ ] **Step 3: Implement icon-aware bundle layout and packaged presentation defaults**

```python
@dataclass(frozen=True)
class MacOSAppBundleLayout:
    ...
    bundled_icon_path: Path

def render_info_plist(*, app_name: str, bundle_id: str, version: str, icon_file: str) -> bytes:
    payload = {
        "CFBundleDisplayName": app_name,
        "CFBundleExecutable": app_name,
        "CFBundleIconFile": icon_file,
        ...
    }
```

```python
def write_unsigned_macos_app_bundle(..., icon_source_path: str | Path) -> dict[str, str]:
    ...
    shutil.copy2(icon_source, layout.bundled_icon_path)
    layout.plist_path.write_bytes(
        render_info_plist(
            app_name=app_name,
            bundle_id=bundle_id,
            version=version,
            icon_file=layout.bundled_icon_path.name,
        )
    )
```

```python
def render_launcher_script(...):
    return "\n".join(
        [
            ...,
            'export MELIX_MENU_BAR_PRESENTATION_MODE="dock-and-tray"',
            f'"$RESOURCES_DIR/{bundled_app_binary_name}" "$@"',
        ]
    )
```

- [ ] **Step 4: Forward the app icon path from the packaging entrypoint and update operator docs**

```python
parser.add_argument(
    "--icon-source-path",
    default=str(
        ROOT / "apps/macos-menubar/Sources/AppMain/Resources/Branding/MelixAppIcon.icns"
    ),
)
...
manifest = write_unsigned_macos_app_bundle(
    ...,
    icon_source_path=args.icon_source_path,
)
```

```markdown
## Packaged macOS UI Surfaces

- The packaged `Melix.app` now launches with both a Dock icon and a tray icon.
- Dock identity comes from `Contents/Resources/MelixAppIcon.icns`.
- The tray still uses the template status icon embedded in the Swift package resources.
```

- [ ] **Step 5: Re-run the targeted Python tests**

Run: `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_macos_app_bundle.py services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py -q`

Expected: PASS with bundle icon copy coverage and package-script forwarding coverage.

- [ ] **Step 6: Commit the packaging slice**

```bash
git add services/mlx-worker-python/worker/productization/macos_app_bundle.py \
  scripts/package_macos_menubar_app.py \
  services/mlx-worker-python/tests/test_macos_app_bundle.py \
  services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py \
  docs/runbooks/platform-packaging-targets.md
git commit -m "feat: package melix dock icon and dock-tray mode"
```

## Verification

- [ ] `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter AppMainBootstrapTests`
- [ ] `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter StatusMenuTests --filter DesktopFoundationViewTests`
- [ ] `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar`
- [ ] `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_macos_app_bundle.py services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py -q`
- [ ] `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" COVERAGE_FILE="$(pwd)/.coverage.macos-logo-shell" uv run --project services/mlx-worker-python --extra mlx coverage run --source=scripts,services/mlx-worker-python/worker/productization,services/mlx-worker-python/tests -m pytest services/mlx-worker-python/tests/test_macos_app_bundle.py services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py -q`
- [ ] `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" COVERAGE_FILE="$(pwd)/.coverage.macos-logo-shell" uv run --project services/mlx-worker-python --extra mlx coverage json -o /tmp/macos_logo_shell_python_coverage.json`
- [ ] `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/macos_logo_shell_python_coverage.json services/mlx-worker-python/worker/productization/macos_app_bundle.py scripts/package_macos_menubar_app.py services/mlx-worker-python/tests/test_macos_app_bundle.py services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py`
- [ ] `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage`
- [ ] `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/AppMain.swift apps/macos-menubar/Sources/AppMain/Branding/MelixBranding.swift apps/macos-menubar/Sources/AppMain/MenuBar/StatusMenu.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopShellChromeView.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift apps/macos-menubar/Tests/MenuBarTests/AppMainBootstrapTests.swift apps/macos-menubar/Tests/MenuBarTests/StatusMenuTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- [ ] `git diff --check`

## Metrics Report

- [ ] Swift targeted tests:
  - record the passing `AppMainBootstrapTests`, `StatusMenuTests`, and `DesktopFoundationViewTests` totals.
- [ ] Swift package regression:
  - record the final `swift test --package-path apps/macos-menubar` suite count.
- [ ] Python targeted tests:
  - record the passing pytest total for the packaging test slice.
- [ ] Python changed-line coverage:
  - record the percentage and covered/total lines from `python_changed_line_coverage.py`.
- [ ] Swift changed-line coverage:
  - record the percentage and covered/total lines from `swift_changed_line_coverage.py`.
- [ ] Performance probes:
  - `N/A` for runtime performance; this transaction uses resource, bundle, and UI rendering evidence instead.
