# Issue 1762 Cookbook Data Root Receipt Slice

## Goal

Add a deterministic cookbook state receipt that resolves cookbook/profile/cache
paths through the same Melix data root on native, container, and remote-shell
runs.

## Scope

- Extend `melix cookbook recommend MODEL_ID --workload WORKLOAD` receipts with a
  `state` object:
  - `data_root`: absolute `MelixHome.rootURL` path.
  - `state_path`: absolute cookbook state path under the Melix state directory.
  - `cache_enabled`: whether cookbook cache/state paths are usable.
  - `disabled_reason`: empty when enabled; a stable reason when the state root is
    missing, not a directory, or not writable.
- Render the same state/cache status in text output.
- Keep this slice read-only. The recommendation command probes path usability
  but does not create directories or write state.
- Keep model ranking, download orchestration, profile cache storage, and App UI
  surfacing out of scope.

## Design

The Swift CLI already owns the first cookbook receipt slice and already resolves
operator state through `MelixHome`, which delegates to `MelixPathLayout`. This
slice reuses that path contract instead of introducing cookbook-specific path
rules.

`MelixCLIRunner.runCookbookRecommend` constructs `MelixHome(environment:)` from
the runner environment and passes it to the cookbook planner. The planner
derives a `state` receipt with:

- `data_root = melixHome.rootURL.path`
- `state_path = melixHome.stateDirectoryURL/cookbook/recommendations.json`
- `cache_enabled = true` only when the state directory exists, is a directory,
  and is writable
- `disabled_reason = state_root_missing | state_root_not_directory |
  state_root_not_writable | ""`

The command remains fail-soft because this receipt is advisory. If the path is
unusable, the recommendation still emits host/backend guidance and records why
cache/state persistence is disabled.

## Verification

Focused Swift tests cover:

- JSON output records `data_root`, `state_path`, `cache_enabled = true`, and an
  empty `disabled_reason` when `MELIX_HOME/state` is writable.
- JSON output records `cache_enabled = false` and
  `disabled_reason = state_root_missing` when the state directory is absent.
- Text output renders the data root and cache status.

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

- `cookbook.plan_ms` remains the command planning duration.
- This slice adds no background sampling loop. Probe overhead is one
  filesystem metadata check against the Melix state directory per recommendation.

## Known Gaps

- This slice does not persist cookbook state or cache files.
- This slice does not audit every existing profile/cache call site. It creates
  the receipt contract those call sites should use in later slices.
