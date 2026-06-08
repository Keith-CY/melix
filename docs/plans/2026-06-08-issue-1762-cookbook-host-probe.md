# Issue 1762 Cookbook Host Probe Source Slice

## Goal

Add the first deterministic cookbook recommendation slice for issue #1762:
when Melix generates a serve/profile recommendation, the host platform must come
from the server-side hardware/runtime probe first, then an explicit operator
override, and only then a browser fallback.

## Scope

- Add a focused CLI cookbook recommendation command:
  `melix cookbook recommend MODEL_ID --workload WORKLOAD [--server-platform PLATFORM] [--server-arch ARCH] [--operator-platform PLATFORM] [--operator-arch ARCH] [--browser-platform PLATFORM] [--browser-arch ARCH] [--json]`.
- Emit a stable receipt with:
  - `schema_version = melix.cookbook.recommendation.v1`
  - `host_platform_source = hardware_probe | explicit_operator_setting | browser_fallback | unavailable`
  - selected host platform and architecture
  - selected backend and command family
  - warnings when Melix falls back to browser hints
- Keep model ranking, downloads, dependency installation, and benchmark artifact
  joining out of scope for this slice.
- Keep the command deterministic and fixture-driven so later cookbook ranking
  can reuse the receipt contract.

## Design

The Swift CLI owns this first slice because recipe planning and operator-facing
fit receipts already live there. The implementation adds a small
`MelixCookbookPlanner` helper in `MelixCLICore`; it does not call the running
control plane and does not mutate state.

The host-selection policy is fail-closed and deterministic:

1. Use non-empty `server-platform` values as `hardware_probe`.
2. Otherwise use non-empty `operator-platform` values as
   `explicit_operator_setting`.
3. Otherwise use non-empty `browser-platform` values as `browser_fallback` and
   emit a warning because browser hints may describe the UI client, not the
   machine serving the model.
4. If no source exists, emit `unavailable`, select the generic command family,
   and warn that the recommendation needs a hardware probe.

Backend and command-family selection remains intentionally simple:

- macOS Apple Silicon (`platform = macos`, `arch = arm64 | arm64e`) selects
  `mlx-native` and `melix server start`.
- Linux selects `python-worker` and `melix server start`.
- Other platforms use `generic-local-runtime` and `melix server start`.

## Verification

Focused Swift tests cover:

- contradictory Windows browser hint with macOS server probe still selects the
  macOS/native path and records `host_platform_source = hardware_probe`;
- explicit operator setting wins when no server probe exists;
- browser fallback emits a warning;
- parser and command codec preserve cookbook recommendation arguments.

Commands:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" \
swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests'

python3 scripts/swift_changed_line_coverage.py \
  --binary .build/arm64-apple-macosx/debug/MelixPackageTests.xctest/Contents/MacOS/MelixPackageTests \
  --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata \
  --diff-from origin/main \
  Sources/MelixCLICore/MelixCLI.swift \
  Sources/MelixCLICore/MelixCLICommandCodec.swift \
  Sources/MelixCLICore/MelixCookbook.swift \
  tests/MelixCLITests/MelixCLIParserTests.swift \
  tests/MelixCLITests/MelixCLIRunnerTests.swift
```

## Metrics

- `cookbook.plan_ms` is emitted in each recommendation receipt.
- No registered PR-scoped performance probe currently watches this new helper;
  the PR scoped performance report should therefore show zero selected probes
  unless the registry changes.

## Known Gaps

- This slice does not implement multi-model ranking, benchmark evidence joins,
  dependency preflight, download readiness, or UI display.
- Future slices should connect the receipt to hardware probes surfaced by the
  running server and to benchmark evidence artifacts.
