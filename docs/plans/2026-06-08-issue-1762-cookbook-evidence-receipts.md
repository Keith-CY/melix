# Issue 1762 Cookbook Evidence Receipt Slice

## Goal

Extend `melix cookbook recommend` with a deterministic evidence receipt that
shows which fit, serve-profile, and benchmark artifacts back the recommendation,
and which artifacts are still unavailable.

## Scope

- Add a top-level `evidence` object to JSON output with:
  - `fit_receipt_schema_version`: the fit receipt contract the recommendation is
    aligned with.
  - `fit_receipt_source`: where the fit evidence came from for this slice.
  - `profile_receipt_schema_version`: the serve-profile receipt contract the
    recommendation is aligned with.
  - `profile_receipt_source`: where the profile evidence came from for this
    slice.
  - `benchmark_receipts`: benchmark or run evidence receipt paths currently
    linked to the recommendation.
  - `missing_receipts`: stable names for evidence links that are not yet
    available.
  - `effective_config_path`: path to a persisted effective config when one is
    available.
- Render the same evidence summary in text output.
- Keep this slice read-only and deterministic. It does not create receipt files,
  perform benchmark runs, download models, or mutate cookbook state.
- Keep multi-model ranking, context-sensitive scoring, mixed-precision footprint
  estimation, dependency installation, and partial-download refusal out of
  scope for this PR.

## Design

The cookbook command already emits deterministic host, backend, and state
receipts from the Swift CLI. This slice adds a small `MelixCookbookEvidenceReceipt`
value produced by the same planner so future ranking and profile joins have a
stable output slot.

For this first evidence join:

- `fit_receipt_schema_version = melix.memory_fit_receipt.v1` because existing
  import, training, benchmark, and eval paths already use that memory-fit
  receipt contract.
- `fit_receipt_source = cookbook.host_selection` because the current cookbook
  only has host/backend fixture evidence, not a model-size-specific fit run.
- `profile_receipt_schema_version = melix.cookbook.profile_receipt.v1` because
  no separate persisted profile receipt exists yet.
- `profile_receipt_source = cookbook.backend_selection` because backend and
  command family are selected by the cookbook planner.
- `benchmark_receipts = []` and `effective_config_path = ""` until later slices
  join real benchmark and effective config artifacts.
- `missing_receipts` includes `effective_config`, `benchmark_receipt`, and
  `model_fit_receipt` to make deferred evidence explicit instead of implying
  that the recommendation is fully evidence-backed.

This keeps the product contract honest: the recommendation is useful, but it
does not claim benchmark or model-fit proof until those receipts are actually
linked.

## Verification

Focused Swift tests cover:

- JSON output includes the evidence receipt, schema versions, sources, empty
  benchmark links, empty effective config path, and missing receipt names.
- Text output renders the evidence sources and missing receipt list.
- Existing host and state receipt tests remain green.

Commands:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" \
swift test --filter 'MelixCLIRunnerTests/cookbookRecommendation'

HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" \
swift test --enable-code-coverage --filter 'MelixCLIParserTests|MelixCLIRunnerTests'

UV_PYTHON=3.12 uv run --project services/mlx-worker-python python \
scripts/swift_changed_line_coverage.py \
  --binary .build/arm64-apple-macosx/debug/melixPackageTests.xctest/Contents/MacOS/melixPackageTests \
  --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata \
  --diff-from origin/main \
  Sources/MelixCLICore/MelixCookbook.swift \
  tests/MelixCLITests/MelixCLIRunnerTests.swift
```

## Metrics

- `cookbook.plan_ms` remains the planning duration measurement.
- Observability mode is `minimal`: the command only emits deterministic receipt
  metadata in the existing CLI response.
- Probe overhead is bounded to constructing a few string fields and arrays per
  recommendation.
- Success target: focused cookbook tests pass, changed-line coverage for touched
  Swift code remains at least 95 percent, and the PR-scoped performance report
  shows zero in-scope regressions.

## Known Gaps

- No real benchmark receipt is linked yet.
- No persisted effective config path is linked yet.
- No model-size-specific memory-fit receipt is linked yet.
- Later #1762 slices should replace the missing receipt markers with real
  artifact paths after model ranking, profile cache, and benchmark joins land.
