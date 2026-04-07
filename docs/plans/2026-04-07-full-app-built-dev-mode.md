# Full App Built Dev Mode

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Melix operators boot the local backend stack together with the native window UI from already-built artifacts, so repeated local restarts do not recompile Swift packages at launch time.

**Architecture:** Keep `scripts/dev_up.sh` as the current backend-only entrypoint and add a separate full-app entrypoint that composes the existing runtime bootstrap with one built-only menubar launch. The Swift control plane remains orchestration truth, the Python worker remains execution truth, and the menubar app stays a thin operator shell that can optionally auto-open the workspace window on startup.

**Tech Stack:** Python launch scripts, shell wrappers, Swift AppKit bootstrap code, pytest, Swift Testing.

---

## Scope

- [x] Add a built-artifact full-app startup entrypoint without changing the default behavior of `scripts/dev_up.sh`.
- [x] Require prebuilt Swift binaries for the full-app path and fail fast with actionable guidance when they are missing.
- [x] Launch `melix-menubar` from the runtime bootstrap and auto-open the workspace window through an explicit startup-surface contract.
- [x] Extend shutdown handling so `scripts/dev_down.sh` also stops the menubar process when the full-app path was used.
- [x] Update operator docs for compile-once and repeated local window-UI restarts.

## Probes And Success Metrics

- [x] Startup artifact probe:
  - `scripts/dev_app_up.py` resolves built binaries for `melix-text-worker-swift`, `melix-control-plane`, and `melix-menubar`.
- [x] Startup contract probe:
  - the menubar process receives `MELIX_MENU_BAR_STARTUP_SURFACE=console` from the full-app bootstrap path.
- [x] UI behavior probe:
  - the default menubar launch remains tray-only, while the `console` startup surface auto-opens the workspace presenter exactly once.
- [x] Shutdown probe:
  - `scripts/dev_down.sh` removes `menubar.pid` after stopping the full-app runtime.
- [x] Operator loop probe:
  - after one prior `swift test` or `swift build`, `bash scripts/dev_app_up.sh` can reopen the full app without invoking `swift run`.

## Implementation Tasks

### Task 1: Full-App Startup Entry Point

**Files:**
- Create: `scripts/dev_app_up.py`
- Create: `scripts/dev_app_up.sh`
- Test: `services/mlx-worker-python/tests/test_dev_app_up_script.py`

- [x] Add a new wrapper script that delegates to a Python entrypoint.
- [x] Reuse the existing runtime layout and process helpers from `scripts/dev_up.py`.
- [x] Start the existing backend stack from built Swift binaries only.
- [x] Resolve and launch the built `melix-menubar` executable with runtime socket paths and the startup-surface override.
- [x] Write `menubar.pid` alongside the existing runtime pid files and log to `menubar.log`.

### Task 2: Menubar Startup Surface Contract

**Files:**
- Modify: `apps/macos-menubar/Sources/AppMain/AppMain.swift`
- Test: `apps/macos-menubar/Tests/MenuBarTests/AppMainBootstrapTests.swift`

- [x] Add a small startup-surface model backed by process environment.
- [x] Preserve the default tray-only startup path.
- [x] Auto-open the existing desktop foundation presenter when `MELIX_MENU_BAR_STARTUP_SURFACE=console`.
- [x] Keep the same presenter wiring used by the status-menu `Open Melix Console` action.

### Task 3: Runtime Shutdown And Operator Docs

**Files:**
- Modify: `scripts/dev_down.sh`
- Modify: `README.md`
- Modify: `docs/runbooks/phase-1-local-stack.md`
- Modify: `docs/runbooks/phase-6-chat-panel.md`

- [x] Stop `menubar.pid` when present.
- [x] Document the compile-once flow and the new full-app restart command.
- [x] Keep the backend-only `scripts/dev_up.sh` workflow documented as the default deterministic stack path.

## Verification

- [x] `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_dev_up_script.py services/mlx-worker-python/tests/test_dev_app_up_script.py -q`
- [x] `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter AppMainBootstrapTests`
- [x] `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" COVERAGE_FILE="$(pwd)/.coverage.full-app-dev" uv run --project services/mlx-worker-python --extra mlx coverage run --source=scripts,services/mlx-worker-python/tests -m pytest services/mlx-worker-python/tests/test_dev_up_script.py services/mlx-worker-python/tests/test_dev_app_up_script.py -q`
- [x] `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" COVERAGE_FILE="$(pwd)/.coverage.full-app-dev" uv run --project services/mlx-worker-python --extra mlx coverage json -o /tmp/full_app_dev_python_coverage.json`
- [x] `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/full_app_dev_python_coverage.json scripts/dev_app_up.py`
- [x] `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter AppMainBootstrapTests`
- [x] `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/AppMain.swift apps/macos-menubar/Tests/MenuBarTests/AppMainBootstrapTests.swift`
- [x] `git diff --check`

## Metrics Report

- [x] Python targeted tests:
  - `30 passed in 10.63s`
- [x] Swift targeted tests:
  - `17 tests in 1 suite passed`
- [x] Python changed-line coverage:
  - `100.00%` (`56/56`) for `scripts/dev_app_up.py`
- [x] Swift changed-line coverage:
  - `98.21%` (`55/56`) across `apps/macos-menubar/Sources/AppMain/AppMain.swift` and `apps/macos-menubar/Tests/MenuBarTests/AppMainBootstrapTests.swift`
- [x] Shell shutdown coverage:
  - `N/A` for line coverage; behavior is validated through the new `test_dev_down_stops_menubar_pid_file` runtime regression.
