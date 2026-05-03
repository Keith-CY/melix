# macOS Launch Opens Workspace

## Status

Implemented.

## Goal

Launching the packaged Melix macOS app should immediately open the main workspace window. The menu bar status item remains available, and an explicit `MELIX_MENU_BAR_STARTUP_SURFACE=tray` override still keeps launch windowless for tray-only development or automation.

## Root Cause

The packaged app did not set `MELIX_MENU_BAR_STARTUP_SURFACE`, and the app bootstrap defaulted missing values to `tray`. In `tray` mode, bootstrap installs the status menu but intentionally does not call the desktop workspace presenter.

The bundle launcher also started `melix-menubar` as a child process after worker startup. LaunchServices tracked the shell launcher as the bundle process while the real Cocoa app ran as an unbundled child process, which prevented normal app/window ownership.

## Implementation

- Default `MenuBarStartupSurface` missing or unknown environment values to `console`.
- Default `MelixMenuBarBootstrap` construction to `.console`.
- Preserve explicit `.tray` behavior for callers and tests that need menu-only launch.
- Set packaged launcher startup surface to `console`.
- Export bundled worker PIDs before handing off to the app process.
- Use `exec` when launching `melix-menubar` so the bundle process becomes the real Cocoa app process.
- Terminate exported bundled worker PIDs from the app termination coordinator when the user quits Melix.

## Verification

- `swift test --package-path apps/macos-menubar --filter AppMainBootstrapTests/bootstrapDefaultsToOpeningWorkspaceOnAppLaunch`
- `swift test --package-path apps/macos-menubar --filter AppMainBootstrapTests`
- `PYTHONPATH=.:services/mlx-worker-python uv run pytest services/mlx-worker-python/tests/test_macos_app_bundle.py -k 'render_launcher_script_starts_bundled_workers_and_app or write_unsigned_macos_app_bundle_writes_self_contained_layout'`
