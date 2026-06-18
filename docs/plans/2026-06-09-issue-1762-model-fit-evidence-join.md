# Issue 1762 Model-Fit Evidence Join Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the cookbook recommendation's `model_fit_receipt` missing marker with a real local receipt path when a matching model-fit artifact already exists.

**Architecture:** Keep `melix cookbook recommend` read-only and deterministic. The Swift cookbook planner scans a shallow evidence directory under `MELIX_HOME`, validates candidate model-fit JSON receipts against the requested model, workload, and selected host, and joins only exact matches into the existing evidence receipt payload.

**Tech Stack:** Swift CLI planner and tests, `Foundation` JSON parsing, Swift Testing.

---

## Scope

- Extend `MelixCookbookRecommendationPlanner` to look for persisted model-fit receipts at:
  - `${MELIX_HOME}/state/cookbook/evidence/model-fit/*.json`
- Treat a candidate as matching only when it has:
  - `schema_version` as a non-empty string.
  - `model_id` equal to the trimmed cookbook request model ID.
  - `workload` equal to the trimmed cookbook request workload.
  - `host.platform`, `host.arch`, and `host.host_platform_source` equal to the planner's selected host.
- Sort candidates by absolute path before matching so duplicate artifacts produce deterministic output.
- When a match exists:
  - Set `evidence.model_fit_receipt_path` to the matched absolute path.
  - Remove `model_fit_receipt` from `evidence.missing_receipts`.
  - Render the same model-fit path in text output.
- When no match exists, preserve the current missing receipt behavior.
- Keep benchmark receipts out of scope for this slice.
- Do not create receipt files, load models, run network calls, or mutate cookbook state.

## Files

- Modify: `Sources/MelixCLICore/MelixCookbook.swift`
  - Add deterministic model-fit discovery and validation helpers.
  - Add `model_fit_receipt_path` to the evidence payload.
  - Add a `Model-fit receipt:` line to text output.
- Modify: `tests/MelixCLITests/MelixCLIRunnerTests.swift`
  - Add a RED test for joining a matching model-fit receipt.
  - Add tests that stale, mismatched, or empty-identity model-fit artifacts remain missing.
- Create: `docs/plans/2026-06-09-issue-1762-model-fit-evidence-join.md`
  - Record this slice's plan, verification, and metrics.

## Task 1: Add RED Tests

- [x] Add `cookbookRecommendationJoinsMatchingModelFitReceipt` to `tests/MelixCLITests/MelixCLIRunnerTests.swift`.
- [x] The test should create `${MELIX_HOME}/state/cookbook/evidence/model-fit/qwen-chat-fit.json` with:

```json
{
  "schema_version": "melix.memory_fit_receipt.v1",
  "model_id": "mlx-community/Qwen3.5-9B-MLX-4bit",
  "workload": "chat",
  "host": {
    "platform": "macos",
    "arch": "arm64",
    "host_platform_source": "hardware_probe"
  },
  "fit": {
    "status": "fits",
    "estimated_memory_gib": 8.75
  }
}
```

- [x] Assert JSON output has `evidence.model_fit_receipt_path` equal to that file path.
- [x] Assert `evidence.missing_receipts` equals `["effective_config", "benchmark_receipt"]`.
- [x] Assert text output includes `Model-fit receipt: <path>` and the shortened missing receipt list.
- [x] Add `cookbookRecommendationKeepsMismatchedModelFitReceiptMissing`.
- [x] The mismatch test should create an artifact for the same model and workload but `host.platform = "linux"`, then assert `model_fit_receipt_path == ""` and `missing_receipts` still contains `model_fit_receipt`.
- [x] Add `cookbookRecommendationIgnoresModelFitReceiptsWithEmptyIdentity`.
- [x] The empty-identity test should create receipts with missing and empty `model_id`/`workload`, run a request with empty model and workload, and assert no model-fit receipt is joined.
- [x] Run the matching test before production changes:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" \
swift test --filter 'MelixCLIRunnerTests/cookbookRecommendationJoinsMatchingModelFitReceipt'
```

Expected: FAIL because `model_fit_receipt_path` is not emitted yet.

## Task 2: Implement Model-Fit Matching

- [x] Add `modelFitReceiptPath` to `MelixCookbookEvidenceReceipt` and encode it as `model_fit_receipt_path`.
- [x] Add helper logic in `MelixCookbook.swift`:
  - Build `melixHome.stateDirectoryURL/cookbook/evidence/model-fit`.
  - Ignore the directory when it does not exist.
  - Read only `.json` files.
  - Parse each file with `JSONSerialization`.
  - Require exact model, workload, and host matches.
  - Return the first match after sorting candidate URLs by path.
- [x] Keep malformed or unreadable JSON files ignored so stale operator state cannot break recommendations.
- [x] Require parsed `model_id` and `workload` to be present and non-empty before comparing them with request values.
- [x] In `makeEvidenceReceipt`, start with `["effective_config", "benchmark_receipt", "model_fit_receipt"]` and remove `model_fit_receipt` only when a path is found.
- [x] In text output, render:

```text
Model-fit receipt: none
```

or:

```text
Model-fit receipt: /absolute/path/to/model-fit.json
```

## Task 3: Verify Locally

- [x] Run the new matching test and confirm PASS:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" \
swift test --filter 'MelixCLIRunnerTests/cookbookRecommendationJoinsMatchingModelFitReceipt'
```

- [x] Run the focused cookbook suite:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" \
swift test --filter 'MelixCLIRunnerTests/cookbookRecommendation'
```

- [x] Run Swift changed-line coverage for touched files:

```bash
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

- [x] Run full local gates before commit:

```bash
make swift-test
make py-test
make integration-test
```

## Metrics

- `cookbook.plan_ms` remains the planning duration probe.
- This slice adds bounded local filesystem scanning of one shallow evidence directory.
- Success metric: focused cookbook tests pass, touched Swift changed-line coverage is at least 95 percent, full local gates pass, and the PR performance report shows zero in-scope regressions.

## Known Gaps

- Benchmark receipts remain missing until benchmark artifact matching lands.
- This slice does not infer matches from existing diagnostics bundles outside the cookbook evidence directory.

## Verification Results

- RED check: `swift test --filter 'MelixCLIRunnerTests/cookbookRecommendationJoinsMatchingModelFitReceipt'` failed before implementation because `model_fit_receipt_path` was absent, `missing_receipts` still included `model_fit_receipt`, and text output did not render a model-fit receipt line.
- Focused Swift: `swift test --filter 'MelixCLIRunnerTests/cookbookRecommendationJoinsMatchingModelFitReceipt'` passed after implementation.
- Focused Swift suite: `swift test --filter 'MelixCLIRunnerTests/cookbookRecommendation'` passed with 15 tests after adding mismatch and empty-identity coverage.
- Swift coverage: `swift test --enable-code-coverage --filter 'MelixCLIParserTests|MelixCLIRunnerTests'` passed with 355 tests after the shared matcher refactor; `scripts/swift_changed_line_coverage.py` reported 100.00 percent changed-line coverage for touched Swift files.
- Full Swift gate: `make swift-test` passed, including the protocol package, Swift text worker package, control-plane focused groups, and macOS menubar package.
- Full Python gate: `make py-test` passed with 3714 tests passed, 14 skipped, and 2 warnings.
- Full integration gate: `make integration-test` passed with 117 tests passed and 1 skipped.
