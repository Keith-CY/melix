# Issue 365 CLI Chain Routing Slice

## Goal

Continue the implementation path for
https://github.com/Keith-CY/melix/issues/365 by making `melix pipeline run`
able to describe the post-training CLI chain in one machine-readable workflow:
adapter training, alignment training, export/publish, quantization, activation,
local chat smoke, and evaluation/benchmark evidence.

Issue 365 is still not complete after this slice. This work adds pipeline
routing and fast dry-run chain coverage; it does not replace the remaining real
local runtime acceptance requirements.

## Scope

### Included

- Add `alignment.train` support to the pipeline command builder so DPO, ORPO,
  CPO, GRPO, and RLHF alignment runs are addressable outside `lora.train`.
- Add post-training model operation routing for `lora.publish`, `quantize`,
  `convert`, and `upload` pipeline steps.
- Preserve existing pipeline behavior for `lora.train`, `lora.activate`,
  `chat.run`, bench, and eval steps.
- Add dry-run coverage proving a post-training chain can be planned with
  step-to-step artifact references across:
  - `lora.train`
  - `alignment.train`
  - `lora.publish`
  - `quantize`
  - `lora.activate`
  - `chat.run`
  - eval or bench evidence steps
- Keep screenshot cleanup scoped to temporary generated screenshot artifacts
  only. Tracked app branding images, evaluation fixtures, docs, and source
  files are not cleanup targets.

### Excluded

- Real local runtime acceptance for every business line.
- GRPO candidate generation from a live policy runtime.
- RLHF reward-model integration from issue 366.
- QAT trainer/export implementation.
- Native Window UI acceptance.
- Closing issue 365.

## Performance And Metrics

This slice changes command construction and dry-run planning only. It should not
add model execution, background polling, or file-system scans beyond the
existing pipeline receipt writes.

Success metrics:

- Pipeline command construction keeps using typed Swift options rather than
  shell string concatenation.
- Pipeline dry-run receipts include stable command IDs for the new post-training
  steps.
- Existing pipeline resume, check, and reference behavior remains unchanged.
- Changed-line coverage for the touched Swift/doc scope is at least 95 percent.

## Verification

Targeted commands:

```bash
swift test --filter MelixCLIRunnerTests
swift test --filter MelixCLIParserTests
git diff --check
```

Coverage and metrics:

```bash
swift test --enable-code-coverage --filter 'MelixCLIRunnerTests|MelixCLIParserTests'
python3 scripts/swift_changed_line_coverage.py \
  --binary .build/arm64-apple-macosx/debug/MelixPackageTests.xctest/Contents/MacOS/MelixPackageTests \
  --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata \
  --diff-from origin/main \
  Sources/MelixCLICore/MelixPipelineRunner.swift \
  tests/MelixCLITests/MelixCLIRunnerTests.swift \
  tests/MelixCLITests/MelixCLIParserTests.swift \
  docs/plans/2026-05-05-issue-365-cli-chain-routing.md
```

Expected changed-line coverage target: at least 95 percent for the changed
Swift scope. Documentation-only lines are reported as N/A when the coverage
tool does not map them to executable statements.

## Remaining Issue 365 Gaps

- Real GRPO policy-runtime candidate generation, scoring, and policy updates.
- RLHF reward-model inference and PPO/reward-guided update integration from
  issue 366.
- QAT training and QAT-aware quantized export.
- Full CLI chain tests backed by real local runtime evidence for every listed
  business line.
- Window UI runnable/inspectable acceptance for every listed business line.
- Final release evidence that separates deterministic/unit/scored-trace results
  from real local runtime results.
