# macOS App Screenshot Capture

**Goal:** Add a repeatable local script that builds Melix.app, captures every
native app surface through deterministic SwiftUI rendering, and writes the PNGs
plus a manifest to a temporary directory.

**Architecture:** Keep app packaging delegated to the existing macOS packaging
script. Add a screenshot-only menubar entrypoint that renders SwiftUI views
off-screen from fixture runtime state, avoiding mouse automation, screen focus,
or screen-recording permissions for the default capture path.

## Scope

- Add a Python orchestration script for build, package, capture, and manifest
  validation.
- Add a menubar screenshot capture entrypoint gated by
  `MELIX_APP_SCREENSHOT_CAPTURE=1`.
- Capture all `DesktopSurface` cases, all `DesktopToolSection` cases, and the
  standalone Command Center.
- Leave live menu bar popover capture out of v1 because it requires AppKit
  window automation and system permissions.

## Verification

- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'AppMainBootstrapTests|AppScreenshotCaptureTests'`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'AppMainBootstrapTests|AppScreenshotCaptureTests'`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_capture_macos_app_screenshots_script.py -q`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" COVERAGE_FILE=/tmp/melix_app_screenshots_python.coverage UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest services/mlx-worker-python/tests/test_capture_macos_app_screenshots_script.py -q`
- `python3 scripts/capture_macos_app_screenshots.py --json`
- `git diff --check`

## Metrics

- Screenshot coverage target: 100% of `DesktopSurface.allCases`,
  `DesktopToolSection.allCases`, and Command Center in the generated manifest.
- PNG validation target: every manifest entry points at an existing PNG file.
- Changed-line coverage target: at least 95% for measurable Swift and Python
  lines in the touched screenshot-capture scope.
