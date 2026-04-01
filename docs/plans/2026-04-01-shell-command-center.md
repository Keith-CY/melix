# Shell And Command Center

## Goal

Replace the old dashboard-led desktop shell with the fixed top navigation `Chat / Image / Server / Tools / API`, add the header shelf, and split global overview into an independent `Command Center` window plus critical banners.

## Scope

- top navigation order and selection state
- centered header navigation
- persistent header shelf
- top-banner escalation rules
- `Command Center` window contract and presentation

## Non-Goals

- server-session control-plane truth changes
- chat-server binding rules
- tools-content migration beyond shell placement

## Required Interfaces

- `DesktopSurface` selection model
- `CommandCenterPresenter` and window builder contract
- `Command Center` read model for health, pressure, recovery items, and recent activity
- top-banner severity model

## Implementation Notes

- remove `Dashboard` from the tab strip entirely
- keep `Command Center` outside the tab strip
- keep the header shelf global and action-oriented
- do not move object-local actions such as `Chat Export` into the header shelf

## Files

- modify `apps/macos-menubar/Sources/AppMain/Dashboard/`
- modify `apps/macos-menubar/Sources/AppMain/AppMain.swift`
- modify `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationPresenterTests.swift`
- modify `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`

## Performance Probes

- `menu.console_open_ms`
- `menu.command_center_open_ms`
- banner-escalation counts once a typed banner model lands

## Verification

- `swift test --package-path apps/macos-menubar --filter DesktopFoundationPresenterTests`
- `swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests`

## Acceptance

- top navigation renders as `Chat / Image / Server / Tools / API`
- no `Dashboard` tab remains
- header shelf exposes exactly `New Chat`, `New Image Job`, `New Server Session`, and `Open Command Center`
- `Command Center` opens as a separate window and reuses a single window instance
- critical states escalate to the top banner while routine states remain in Command Center or the inspector
