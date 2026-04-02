# Sidecar Verification Unblock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unblock repository verification for the sidecar-service reuse slice by isolating the hanging Swift control-plane test path, restoring touched-scope coverage evidence, and only then performing the requested local squash merge.

**Architecture:** Treat this as a verification and evidence repair slice rather than a product-surface rewrite. Keep the service-first Python sidecar changes intact, fix only the smallest Swift or test cleanup needed to let `services/control-plane-swift` finish, and measure touched-scope coverage with the repository-owned changed-line coverage scripts instead of coarse whole-file percentages.

**Tech Stack:** Swift 6, Swift Testing, Python 3.13, pytest, coverage.py, repository coverage helper scripts, local `make` verification targets.

---

## Scope Notes

- Do not change the service-first sidecar runtime layout unless a failing test proves the implementation is wrong.
- Prefer test-harness or lifecycle cleanup fixes over control-plane behavior changes.
- Use changed-line coverage for the touched Python scope and record the exact command output.

## Performance Probes And Success Metrics

- `swift_test.control_plane_completion`
- `swift_test.hanging_suite_filter`
- `coverage.changed_line_percent`
- `verification.full_repo_green`

### Task 1: Isolate The Hanging Swift Control-Plane Test Path

**Files:**
- Modify: `services/control-plane-swift/Tests/...` only if a focused reproduction proves a leaked task, stream, or event-loop lifecycle bug.
- Modify: `services/control-plane-swift/Sources/...` only if the root cause lives in production lifecycle cleanup rather than the test harness.
- Update: `docs/plans/2026-04-02-sidecar-verification-unblock.md`

- [x] Reproduce the hang with focused `swift test --package-path services/control-plane-swift --filter ...` runs until the smallest hanging suite or test is identified.
- [x] Capture fresh evidence for the blocking suite, including the exact filter command and whether the process idles in `CFRunLoopRun` / `kevent`.
- [x] Write or tighten a focused failing Swift test if the root cause needs a more deterministic reproduction than the hanging suite itself.
- [x] Implement the smallest lifecycle fix needed to let the focused reproduction exit cleanly.
- [x] Re-run the focused Swift filter set and then `swift test --package-path services/control-plane-swift` to confirm clean completion.

Task 1 execution notes:

- The fresh reproduction shifted from `services/control-plane-swift` itself to the downstream menubar package. The smallest blocking reproduction was `swift test --package-path apps/macos-menubar --filter ControlPlaneXPCClientTests`, where the original test expected a worker-only `model.state_changed` event on the local fast path.
- The focused fix was to align the test with the real control-plane behavior, keep explicit `unsubscribe` cleanup in worker-backed subscription tests, and tighten menubar lifecycle cleanup so the view-model cancels the subscription task during teardown without changing the service-first runtime design.
- Focused evidence after the fix:
  - `swift test --package-path apps/macos-menubar --filter ControlPlaneXPCClientTests` -> pass (`15 tests`)
  - `swift test --package-path apps/macos-menubar` -> pass (`139 tests`)
  - `swift test --package-path services/control-plane-swift` -> pass (`469 tests`)

### Task 2: Restore Touched-Scope Coverage Evidence

**Files:**
- Modify: `services/mlx-worker-python/tests/test_install_assets.py`
- Modify: `services/mlx-worker-python/tests/test_dev_up_script.py`
- Modify: `services/mlx-worker-python/tests/test_runtime_edges.py`
- Modify: `scripts/python_changed_line_coverage.py` only if the existing changed-line script cannot measure this slice correctly without a bugfix.
- Update: `docs/plans/2026-04-02-sidecar-verification-unblock.md`

- [x] Compute changed Python lines for the current sidecar-service diff and identify any uncovered executable lines.
- [x] Add or tighten Python tests for the uncovered sidecar-service paths, especially `build_server()` environment propagation and sidecar runtime layout derivation, only after proving the missing lines are real gaps.
- [x] Run the focused Python tests and verify they pass.
- [x] Run `coverage run` for the focused Python tests and then `python3 scripts/python_changed_line_coverage.py ...` for the touched Python files.
- [x] Record the exact changed-line coverage percentage and confirm it meets the repository `>=95%` gate.

Task 2 execution notes:

- The initial changed-line coverage run reported `92.45% (49/53)` across `scripts/dev_up.py`, `scripts/install_local_product.py`, `worker/grpc_server.py`, and `worker/productization/install_assets.py`.
- Tightened Python coverage added sidecar-specific assertions for:
  - runtime environment export of `MELIX_SERVICE_INSTANCE_NAME`
  - `install_local_product.py` forwarding `--service-instance-name`
  - local-product environment script emission for sidecar layouts
- Focused verification:
  - `uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_dev_up_script.py services/mlx-worker-python/tests/test_install_assets.py services/mlx-worker-python/tests/test_install_local_product_script.py -q` -> pass (`28 passed`)
- Final Python changed-line coverage:
  - `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/melix-sidecar-python-coverage.json scripts/dev_up.py scripts/install_local_product.py services/mlx-worker-python/worker/grpc_server.py services/mlx-worker-python/worker/productization/install_assets.py`
  - Result: `100.00% (53/53)`

### Task 3: Re-run Repository Verification And Merge

**Files:**
- Update: `docs/plans/2026-04-02-sidecar-verification-unblock.md`

- [x] Run the required repository verification commands again:
  - `make swift-test`
  - `make py-test`
  - `make integration-test`
- [x] Record the changed-scope metrics report for this slice.
  - `swift_test.control_plane_completion`: pass or fail with exact command evidence
  - `coverage.changed_line_percent`: exact changed-line coverage output
  - Runtime metrics: `N/A` if no runtime probe changed in this slice beyond verification and layout wiring
- [x] If and only if all verification is green, switch to local `main`, perform the requested squash merge from the current detached worktree state, and create one local commit.
- [ ] If any verification remains red, stop without merging and report the blocker with the fresh evidence.

Task 3 execution notes:

- Fresh final-state repository verification:
  - Detached-worktree verification before the squash:
    - `make swift-test` -> pass
    - `make py-test` -> pass (`341 passed`)
    - `make integration-test` -> pass (`54 passed in 610.62s`)
  - Fresh local-`main` verification after clearing stale Swift 6.2.3 build artifacts and stabilizing the menubar SwiftUI render assertions for the Swift 6.3 toolchain:
    - `make swift-test` -> pass
    - `make py-test` -> pass (`341 passed in 1.25s`)
    - `make integration-test` -> pass (`54 passed in 612.39s`)
- Changed-scope metrics report:
  - `swift_test.control_plane_completion`: pass
    - `swift test --package-path services/control-plane-swift` -> pass (`469 tests`)
    - `swift test --package-path apps/macos-menubar` -> pass (`139 tests`)
  - `swift_test.hanging_suite_filter`: pass
    - `swift test --package-path apps/macos-menubar --filter ControlPlaneXPCClientTests` -> pass (`15 tests`)
  - `coverage.changed_line_percent`:
    - Python: `100.00% (53/53)`
    - Swift control-plane touched scope: `100.00% (10/10)`
    - Swift menubar touched scope: `100.00% (14/14)`
    - Combined Swift touched scope: `100.00% (24/24)`
  - Runtime metrics: `N/A` for this verification-only slice beyond sidecar layout wiring and test-harness cleanup.
  - `verification.full_repo_green`: pass
