# Issue 365 Window Acceptance Matrix Slice

## Goal

Continue https://github.com/Keith-CY/melix/issues/365 by making the native
Window UI evidence bundle enumerate every required business line and by adding
an explicit PTQ/QAT mode selector to the Window quantization surface.

Issue 365 is still not complete after this slice. The evidence added here is
Window UI routing and inspectability evidence. It does not claim final
real-local-runtime release readiness for any business line.

## Scope

### Included

- Add a Window quantization mode state for `ptq` and `qat`.
- Show the mode selector beside the existing quantization profile selector.
- Forward `quantization_mode` and `source_artifact_kind` through Window model
  operations so PTQ/QAT requests are explicit.
- Record adapter-derived source artifact hints for QAT when a saved LoRA job is
  selected.
- Extend the Phase 8 Window UI acceptance bundle with all 10 Issue 365 business
  lines:
  - LoRA, QLoRA, and DoRA supervised adapter workflows.
  - DPO, ORPO, CPO, GRPO, and RLHF alignment workflows.
  - PTQ quantized local inference workflow.
  - QAT/QAT-aware quantized local inference workflow.
- Mark the matrix evidence as non-release-ready until real local runtime runs
  succeed for the same cases.

### Excluded

- Real GRPO/RLHF policy updates.
- Reward-model training artifacts from issue 366.
- MLX-native full-tensor QAT execution.
- Full real-runtime CLI or Window acceptance execution for every business line.
- Screenshot artifact preservation.
- Closing issue 365.

## Performance And Metrics

This slice only adds UI state, model-operation request metadata, and JSON
evidence construction during an explicit acceptance run. It does not add
background polling or new model execution work.

Success metrics:

- Quantization command construction keeps the existing unit-test dispatch path.
- The Window acceptance bundle contains exactly 10 business-line entries.
- Each matrix entry records visible/selectable/runnable/inspectable routing
  state and keeps `release_ready=false`.
- Changed-scope tests remain green with at least 95 percent changed-line
  coverage for the touched Swift scope.

## Verification

Targeted commands:

```bash
swift test --package-path apps/macos-menubar --filter 'Phase8WindowUIAcceptanceRunnerTests|RuntimeViewModelTests'
git diff --check
```

Coverage and metrics:

```bash
swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'Phase8WindowUIAcceptanceRunnerTests|RuntimeViewModelTests'
python3 scripts/swift_changed_line_coverage.py \
  --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests \
  --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata \
  --diff-from origin/main \
  apps/macos-menubar/Sources/AppMain/Acceptance/Phase8WindowUIAcceptanceRunner.swift \
  apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift \
  apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift \
  apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift \
  apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift
```

Results on 2026-05-06:

- `swift test --package-path apps/macos-menubar --filter 'Phase8WindowUIAcceptanceRunnerTests|RuntimeViewModelTests'`:
  254 tests passed in 2 suites.
- `swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'Phase8WindowUIAcceptanceRunnerTests|RuntimeViewModelTests'`:
  254 tests passed in 2 suites and wrote Swift coverage data.
- `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main apps/macos-menubar/Sources/AppMain/Acceptance/Phase8WindowUIAcceptanceRunner.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift docs/plans/2026-05-06-issue-365-window-acceptance-matrix.md`:
  100.00 percent total changed-line coverage, 340/340 executable lines.
- `git diff --check`: passed.

## Remaining Issue 365 Gaps

- Real local runtime evidence for every CLI and Window business line.
- Final populated release evidence bundle.
- GRPO/RLHF policy-update implementation and reward-model artifact integration.
- MLX-native full QAT backend execution and release-gated evidence.
