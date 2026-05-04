# Issue 365 Window Alignment Routing Slice

## Goal

Continue the implementation path for
https://github.com/Keith-CY/melix/issues/365 by making the native Window
training surface expose the alignment business lines already present in the CLI
contract and route those modes through `melix alignment train` when the desktop
is backed by the CLI workflow runner.

Issue 365 is still not complete after this slice. This work only closes one
Window UI and CLI routing gap; it does not implement the remaining trainer,
quantization, or real-runtime acceptance requirements.

## Scope

### Included

- Add CPO, GRPO, and RLHF to the desktop training mode selector alongside
  LoRA, QLoRA, DoRA, DPO, ORPO, and CPT.
- Add desktop state and persisted draft fields for alignment-specific
  parameters:
  - `grpo_candidate_count`
  - `reference_model_path`
  - `reward_model_manifest_path`
  - `kl_penalty`
- Show alignment-specific parameter inputs in the training draft form when an
  alignment mode is selected.
- Route DPO, ORPO, CPO, GRPO, and RLHF through `MelixCLICommand.alignmentTrain`
  when a CLI workflow runner is configured.
- Preserve existing direct control-plane model-operation behavior by forwarding
  the same alignment ext fields to `train_lora`.
- Remove the temporary LoRA marketing screenshot renderer test now that the
  screenshot artifacts are no longer part of this slice.

### Excluded

- Full DPO, ORPO, CPO, GRPO, or RLHF optimizer implementation.
- Reward-model training or reward-model artifact generation from issue 366.
- Real local runtime acceptance for every business line.
- Closing issue 365.

## Performance And Metrics

This slice changes only desktop state construction, command routing, and
SwiftUI form composition. It does not add model execution work or background
polling. The performance probe is therefore command-construction latency and
view-model action dispatch staying within the existing unit-test path.

Success metrics:

- Desktop mode coverage includes all Issue 365 training business lines.
- CLI-backed desktop training uses `alignment.train` for DPO/ORPO/CPO/GRPO/RLHF.
- Direct desktop training still forwards alignment parameters through the
  control-plane model operation ext map.
- Changed-scope tests remain green.

## Verification

Targeted commands:

```bash
swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests
swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests
git diff --check
```

Coverage and metrics:

```bash
swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'
python3 scripts/swift_changed_line_coverage.py \
  --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests \
  --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata \
  Sources/MelixCLICore/LoraTrainingJobStore.swift \
  apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift \
  apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift \
  apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift \
  apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift
```

Expected changed-line coverage target: at least 95 percent for the changed
Swift scope.

## Remaining Issue 365 Gaps

- Full DPO, ORPO, and CPO optimizer loops.
- GRPO candidate generation, scoring, and policy updates.
- RLHF integration with reward-model artifacts from issue 366.
- Real PTQ/QAT local inference release evidence.
- Complete CLI chain tests with real local runtime evidence for every business
  line.
- Window UI runnable/inspectable acceptance with real local runtime evidence
  for every business line.

## Screenshot Cleanup

The tracked `TempLoRAScreenshotTests` helper was a temporary marketing
screenshot generator for earlier LoRA visual polish work. This slice removes
that test file and keeps the generated screenshot directories ignored. Product
fixtures and app branding images are not screenshot artifacts and remain in the
repository.
