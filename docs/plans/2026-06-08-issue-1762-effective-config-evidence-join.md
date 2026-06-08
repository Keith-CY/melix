# Issue 1762 Effective Config Evidence Join Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the cookbook recommendation's `effective_config` missing marker with a real local receipt path when a matching effective-config artifact already exists.

**Architecture:** Keep `melix cookbook recommend` read-only and deterministic. The Swift cookbook planner scans a worktree-local evidence directory under `MELIX_HOME`, validates candidate `effective-config.json` files against the requested model, workload, and selected host, and joins only exact matches into the existing evidence receipt payload.

**Tech Stack:** Swift CLI planner and tests, `Foundation` JSON parsing, Swift Testing.

---

## Scope

- Extend `MelixCookbookRecommendationPlanner` to look for persisted effective config receipts at:
  - `${MELIX_HOME}/state/cookbook/evidence/effective-configs/*.json`
- Treat a candidate as matching only when it has:
  - `schema_version` as a non-empty string.
  - `model_id` equal to the trimmed cookbook request model ID.
  - `workload` equal to the trimmed cookbook request workload.
  - `host.platform`, `host.arch`, and `host.host_platform_source` equal to the planner's selected host.
- Sort candidates by absolute path before matching so duplicate artifacts produce deterministic output.
- When a match exists:
  - Set `evidence.effective_config_path` to the matched absolute path.
  - Remove `effective_config` from `evidence.missing_receipts`.
  - Render the same effective config path in text output.
- When no match exists, preserve the current missing receipt behavior.
- Keep benchmark receipts and model-fit receipts out of scope for this slice.
- Do not create receipt files, load models, run network calls, or mutate cookbook state.

## Files

- Modify: `Sources/MelixCLICore/MelixCookbook.swift`
  - Add deterministic effective-config discovery and validation helpers.
  - Pass `CookbookRecommendOptions`, selected host, and `MelixHome` into evidence creation.
  - Add an `Effective config:` line to text output.
- Modify: `tests/MelixCLITests/MelixCLIRunnerTests.swift`
  - Add a RED test for joining a matching effective config receipt.
  - Add a test that stale or mismatched host artifacts remain missing.
  - Add a review-followup test that receipts with missing or empty identity fields cannot match empty request values.
- Create: `docs/plans/2026-06-08-issue-1762-effective-config-evidence-join.md`
  - Record this slice's plan, verification, and metrics.

## Task 1: Add RED Tests

- [x] Add `cookbookRecommendationJoinsMatchingEffectiveConfigReceipt` to `tests/MelixCLITests/MelixCLIRunnerTests.swift`.
- [x] The test should create `${MELIX_HOME}/state/cookbook/evidence/effective-configs/qwen-chat.json` with:

```json
{
  "schema_version": "melix.diagnostics.effective_config.v1",
  "model_id": "mlx-community/Qwen3.5-9B-MLX-4bit",
  "workload": "chat",
  "host": {
    "platform": "macos",
    "arch": "arm64",
    "host_platform_source": "hardware_probe"
  },
  "serving_profile": {
    "selected_backend": "mlx-native"
  }
}
```

- [x] Assert JSON output has `evidence.effective_config_path` equal to that file path.
- [x] Assert `evidence.missing_receipts` equals `["benchmark_receipt", "model_fit_receipt"]`.
- [x] Assert text output includes `Effective config: <path>` and the shortened missing receipt list.
- [x] Add `cookbookRecommendationKeepsMismatchedEffectiveConfigReceiptMissing`.
- [x] The mismatch test should create an artifact for the same model and workload but `host.platform = "linux"`, then assert `effective_config_path == ""` and `missing_receipts` still contains `effective_config`.
- [x] Run the matching test before production changes:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" \
swift test --filter 'MelixCLIRunnerTests/cookbookRecommendationJoinsMatchingEffectiveConfigReceipt'
```

Expected: FAIL because `effective_config_path` is still empty.

## Task 2: Implement Effective Config Matching

- [x] Change `makePayload` and `makeText` to call:

```swift
let evidence = makeEvidenceReceipt(options: options, host: host, melixHome: melixHome)
```

- [x] Add helper logic in `MelixCookbook.swift`:
  - Build `melixHome.stateDirectoryURL/cookbook/evidence/effective-configs`.
  - Ignore the directory when it does not exist.
  - Read only `.json` files.
  - Parse each file with `JSONSerialization`.
  - Require exact model, workload, and host matches.
  - Return the first match after sorting candidate URLs by path.
- [x] Keep malformed or unreadable JSON files ignored so stale operator state cannot break recommendations.
- [x] Require parsed `model_id` and `workload` to be present and non-empty before comparing them with request values.
- [x] In `makeEvidenceReceipt`, start with `["effective_config", "benchmark_receipt", "model_fit_receipt"]` and remove `effective_config` only when a path is found.
- [x] In text output, render:

```text
Effective config: none
```

or:

```text
Effective config: /absolute/path/to/effective-config.json
```

## Task 3: Verify Locally

- [x] Run the new matching test and confirm PASS:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" \
swift test --filter 'MelixCLIRunnerTests/cookbookRecommendationJoinsMatchingEffectiveConfigReceipt'
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

- [x] Run full local gates before commit when feasible:

```bash
make swift-test
make py-test
make integration-test
```

## Metrics

- `cookbook.plan_ms` remains the planning duration probe.
- This slice adds bounded local filesystem scanning of one shallow evidence directory.
- Success metric: focused cookbook tests pass, touched Swift changed-line coverage is at least 95 percent, full local gates pass or have a documented blocker, and the PR performance report shows zero in-scope regressions.

## Verification Results

- RED check: `swift test --filter 'MelixCLIRunnerTests/cookbookRecommendationJoinsMatchingEffectiveConfigReceipt'` failed before implementation because `effective_config_path` remained empty and `missing_receipts` still included `effective_config`.
- Focused Swift: `swift test --filter 'MelixCLIRunnerTests/cookbookRecommendation'` passed with 12 tests after adding missing/empty receipt identity coverage.
- Swift coverage: `swift test --enable-code-coverage --filter 'MelixCLIParserTests|MelixCLIRunnerTests'` passed with 352 tests; `scripts/swift_changed_line_coverage.py` reported 99.51 percent changed-line coverage for touched Swift files.
- Python gate: `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest` passed with 4134 tests and 15 skips after synchronizing the stale Phase 8 acceptance bundle expectation from `--model-id` to the current `server session update --model` CLI contract.
- Integration gate: `make integration-test` passed with 117 tests and 1 skip.
- Python changed-line coverage for the stale Phase 8 test expectation is N/A because the only changed Python line is a non-executable expected-argv string literal; the focused test covering that expectation passed.

## Known Gaps

- Benchmark receipts remain missing until benchmark artifact matching lands.
- Model-fit receipts remain missing until model-specific fit evidence is joined.
- This slice does not infer matches from existing diagnostics bundles outside the cookbook evidence directory.
