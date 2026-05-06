# Issue 365 Window Acceptance Matrix Slice

## Goal

Continue https://github.com/Keith-CY/melix/issues/365 by making the native
Window UI evidence bundle enumerate every required business line and by adding
an explicit PTQ/QAT mode selector to the Window quantization surface. The
follow-up real-evidence bridge makes the Window UI bundle consume the same
Issue 365 CLI acceptance bundle so each Window business line can chain to the
matching real local runtime case.

Issue 365 is still not complete after this slice. The evidence added here is
Window UI routing and inspectability evidence plus a chained CLI real-runtime
release gate. A Window business line is only marked `release_ready=true` when
the configured CLI bundle is `execution_mode=real`, the top-level CLI bundle is
`release_ready=true`, and the matching CLI case is `status=succeeded` with
`release_ready=true`. This does not mean every business line was independently
clicked through in the Window UI; it means the Window route is visible,
selectable, runnable, and inspectable while the same business line is backed by
the release-ready CLI real-runtime case.

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
- Map each Window business-line case to the corresponding Issue 365 CLI case:
  - `base_lora_export_local_inference` -> `lora_export_inference`
  - `base_qlora_export_local_inference` -> `qlora_export_inference`
  - `base_dora_export_local_inference` -> `dora_export_inference`
  - `lora_dpo_export_local_inference` -> `lora_dpo_export_inference`
  - `lora_orpo_export_local_inference` -> `lora_orpo_export_inference`
  - `lora_cpo_export_local_inference` -> `lora_cpo_export_inference`
  - `lora_grpo_export_local_inference` -> `lora_grpo_export_inference`
  - `lora_rlhf_export_local_inference` -> `lora_rlhf_export_inference`
  - `lora_preference_ptq_local_inference` -> `lora_preference_ptq_quantized_inference`
  - `qat_quantized_local_inference` -> `qat_quantized_inference`
- Keep the matrix evidence non-release-ready when the CLI bundle is missing
  real execution mode, is not top-level release-ready, lacks the mapped case,
  or has a mapped case that is not succeeded and release-ready.

### Excluded

- Real GRPO/RLHF policy updates.
- Reward-model training artifacts from issue 366.
- MLX-native full-tensor QAT execution.
- Independent Window click-through execution for every business line beyond the
  existing route/runnable/inspectable checks.
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
  state and the mapped CLI case id/status/evidence tier.
- Matrix entries only use
  `evidence_level=window_route_matrix_with_real_cli_runtime` and
  `release_ready=true` when the mapped real CLI case is release-ready under a
  top-level release-ready real CLI bundle.
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

- Final populated release evidence bundle.
- GRPO/RLHF policy-update implementation and reward-model artifact integration.
- MLX-native full QAT backend execution and release-gated evidence.
- Independent Window click-through execution for every business line beyond the
  route-level acceptance checks.
