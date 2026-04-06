# M10.4 Session Lifecycle Integration Evidence

Status: completed on 2026-04-05. Melix now owns a repository-local session lifecycle smoke
executable, live integration coverage against real worker processes, and an operator runbook for
pause, idle sleep, wake, and restart recovery.

## Goal

Close the session-lifecycle milestone with live-path coverage, metrics, and operator runbook evidence.

## Scope

- add lifecycle smoke paths and restart coverage
- record pause, sleep, and wake metrics
- document operator diagnosis and recovery steps

## Files

- update `Package.swift`
- update `Sources/MelixCLICore/`
- add `Sources/MelixSessionLifecycleSmoke/`
- update `tests/integration/`
- update `tests/MelixCLITests/`
- update `docs/runbooks/`
- update `docs/README.md`

## Implementation Notes

- Evidence should include idle-to-sleep and wake-to-ready timings.
- Recovery guidance should separate transient reconnect issues from genuine lifecycle faults.
- Metrics must remain machine-readable and reproducible.
- The final smoke path keeps one `ControlPlaneService` instance alive for the whole scenario so
  pause, idle sleep, request-activity wake, and restart recovery all observe the same runtime
  session state instead of recreating lifecycle state per command invocation.
- The integration wrapper starts real worker processes, stops the auxiliary HTTP control plane, and
  then runs `melix-session-lifecycle-smoke` against the live worker sockets to preserve a real
  execution path without adding new admin HTTP endpoints.

## Verification

- `make integration-test`
- session-lifecycle smoke command for the touched scope
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter SessionLifecycleSmokeRunnerTests`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --filter SessionLifecycleSmokeRunnerTests`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest tests/integration/test_session_lifecycle_integration.py -q`
- `make swift-test`
- `make integration-test`
- `python3 scripts/swift_changed_line_coverage.py --binary .build/arm64-apple-macosx/debug/melixPackageTests.xctest/Contents/MacOS/melixPackageTests --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata Package.swift Sources/MelixCLICore/LocalRuntimeFactory.swift Sources/MelixCLICore/MelixCLI.swift Sources/MelixCLICore/SessionLifecycleSmokeRunner.swift Sources/MelixCLICore/SessionLifecycleSmokeCommand.swift Sources/MelixSessionLifecycleSmoke/main.swift tests/MelixCLITests/SessionLifecycleSmokeRunnerTests.swift`
- `git diff --check`

## Acceptance

- The session lifecycle has live integration coverage and a reproducible metrics report.
- Runbooks explain how to inspect and recover lifecycle failures.

## Verification Results

- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter SessionLifecycleSmokeRunnerTests`: `14 tests in 1 suite passed after 3.005 seconds`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --filter SessionLifecycleSmokeRunnerTests`: `14 tests in 1 suite passed after 3.002 seconds`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest tests/integration/test_session_lifecycle_integration.py -q`: `1 passed in 93.36s`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" COVERAGE_FILE=/tmp/m10_4_python.coverage UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python coverage run --include='tests/integration/test_session_lifecycle_integration.py' -m pytest tests/integration/test_session_lifecycle_integration.py -q`: `1 passed in 40.92s`
- `make swift-test`: pass
- `make integration-test`: `60 passed in 738.98s (0:12:18)`
- `python3 scripts/swift_changed_line_coverage.py ...`: `98.30% (752/765)` across the touched Swift executable scope
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m10_4_python_coverage.json tests/integration/test_session_lifecycle_integration.py`: `100.00% (46/46)`

## Metrics Report

- lifecycle smoke metrics:
  - `lifecycle.pause_ack_ms`
  - `lifecycle.idle_to_light_sleep_ms`
  - `lifecycle.wake_to_ready_ms`
  - `lifecycle.restart_recovery_ms`
- control-plane lifecycle counters and timings:
  - `control_plane.server_start_ms`
  - `control_plane.server_pause_ms`
  - `control_plane.server_resume_ms`
  - `control_plane.server_wake_ms`
  - `control_plane.server_stop_ms`
  - `control_plane.server_idle_policy_ms`
- changed-line coverage for the touched executable scope:
  - Swift CLI and smoke harness scope: `98.30%` (`752/765`)
  - Python integration scope: `100.00%` (`46/46`)
