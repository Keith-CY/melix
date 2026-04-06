# M13.4 API Reference And Quick-Start Onboarding

## Goal

Add product-owned API reference material and quick-start examples for supported local API consumers.

## Scope

- project supported endpoint reference from control-plane truth
- add curl, Python, and JavaScript quick-start examples
- keep onboarding aligned with supported OpenAI, Anthropic, and Ollama surfaces

## Files

- update `apps/macos-menubar/Sources/AppMain/`
- update `services/control-plane-swift/Sources/HTTPGateway/`
- update `docs/README.md`
- update `docs/runbooks/`

## Implementation Notes

- Reference material should describe only shipped or supported surfaces.
- Snippets should remain stable enough for automated smoke execution where practical.
- Onboarding should emphasize local endpoint behavior and auth expectations clearly.

## Executable Slices

### Slice 1: Typed API Onboarding Summary

- add a typed `api_onboarding` summary to `ServerSnapshot`
- project shipped endpoint reference and supported compatibility surfaces from control-plane truth
- replace the static desktop API endpoint catalog with the typed snapshot summary
- generate session-aware curl, Python, and JavaScript quick-start snippets from the typed summary
  plus selected server-session auth and base-URL state
- keep Ollama guidance explicit about the current compatibility boundary when native `/api/*`
  routes are not shipped

Status: slice 1 completed on 2026-04-06.

### Slice 2: Onboarding Example Smoke Verification

- add a repo-owned smoke script for the canonical `/health`, `/v1/responses`, and `/v1/messages`
  quick-start examples
- exercise the same example semantics in deterministic integration coverage so CI detects drift
- keep desktop quick-start helper tests aligned with the example payload text, auth behavior, and
  endpoint shapes used by the smoke script

Status: completed on 2026-04-06.

## Verification

- `make proto`: pass
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'ControlPlaneServiceTests'`: `160 tests in 1 suite passed`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'DesktopFoundationViewTests'`: `69 tests in 1 suite passed`
- `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/HTTPGateway/APIOnboardingSnapshotSource.swift services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`: `100.00%` (`38/38`)
- `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationState.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`: `96.51%` (`746/773`)
- aggregate touched-scope changed-line coverage: `96.67%` (`784/811`)
- `git diff --check`: pass
- `make swift-test`: failed outside the touched scope when `services/mlx-text-worker-swift` exited with unexpected signal `11` during `WorkerScaffoldTests`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/m13_api_onboarding_smoke.py --json`: pass with `/health`, `/v1/responses`, and `/v1/messages` all returning `200`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest tests/test_m13_api_onboarding_smoke.py tests/integration/test_api_onboarding_examples.py -q`: `16 passed in 11.69s`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'DesktopFoundationViewTests'`: `69 tests in 1 suite passed`
- `make py-test`: `487 passed in 44.61s`
- `make integration-test`: `67 passed in 898.58s (0:14:58)`
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m13_api_onboarding_coverage.json scripts/m13_api_onboarding_smoke.py tests/test_m13_api_onboarding_smoke.py tests/integration/test_api_onboarding_examples.py`: `100.00%` (`163/163`)
- `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`: `100.00%` (`119/119`)
- aggregate touched-scope changed-line coverage for slice 2: `100.00%` (`282/282`)

## Acceptance

- API reference and quick-start material are product-visible, accurate, and maintainable.
- Example snippets match live endpoint behavior.
