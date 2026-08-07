# Swift 6.3 CI Toolchain Baseline

## Goal

Make every GitHub-hosted macOS workflow that builds Melix Swift code select and
verify the same Swift 6.3 toolchain required by the repository's current MLX
dependency graph.

## Context

`mlx-swift` 0.31.6 declares Swift tools version 6.3. The GitHub-hosted
`macos-15` arm64 image used by Melix defaults to Xcode 16.4 / Swift 6.1.
Its newest bundled Xcode, 26.3, still exposes only Swift 6.2.4. Neither compiler
can parse the dependency's Swift 6.3 package manifest. The GitHub-hosted
`macos-26` arm64 image includes Xcode 26.5, which matches the repository's
local pre-commit baseline and exposes Apple Swift 6.3.

Local developer machines are not changed by this plan. The repository's local
pre-commit gate continues to use the operator-selected Xcode and verifies the
full test suite on the supported host.

## Architecture

- `.github/actions/setup-melix-swift-toolchain/action.yml` is the single
  repository-owned source of truth for the GitHub Actions Xcode and Swift
  baseline.
- Swift-building jobs run on GitHub's `macos-26` arm64 label. Jobs that do not
  build Swift remain on their existing runner so this migration does not expand
  unrelated CI scope.
- The action selects `/Applications/Xcode_26.5.app/Contents/Developer` through
  `DEVELOPER_DIR`, verifies that `xcrun swift --version` reports Apple Swift
  6.3, and fails closed if either contract drifts.
- The action exposes a stable compiler cache namespace. Swift build caches use
  that namespace and do not fall back to caches produced by the previous Swift
  6.1 default.
- PR, scheduled regression, release gate, app packaging, benchmark/evaluation,
  and macOS scoped-performance jobs all select the same toolchain before
  resolving or building Swift packages.
- Base-versus-head performance workflows use the head revision's toolchain
  action for both checkouts so compiler choice cannot bias the comparison.

## Delivery Slices

1. Add the repository-local toolchain action and validate its failure modes.
2. Wire every macOS Swift build workflow to the action and isolate Swift caches
   by compiler baseline.
3. Verify the dependency update under the exact hosted-runner toolchain and
   keep the PR evidence synchronized with the terminal CI result.

## Performance Probes And Success Metrics

This is CI-only configuration and does not change a Melix runtime code path, so
no production performance probe is applicable. The measurement points are the
toolchain action log, the emitted cache namespace, and the existing scoped
performance report.

Success requires:

- every Swift-building job and Swift performance probe to run on `macos-26`;
- the action to report Xcode 26.5 and Apple Swift 6.3.x;
- `mlx-swift` 0.31.6 to resolve without a tools-version error;
- all PR Swift shards and integration tests to pass;
- no Swift cache restored from a Swift 6.1 namespace; and
- the PR-scoped performance report to contain no in-scope regression or
  verification failure.

## Verification

- `actionlint`
- `git diff --check`
- `make proto`
- `make swift-test`
- `make py-test`
- `make integration-test`
- the repository pre-commit scoped performance report
- terminal GitHub Actions results for the synchronized PR head

## Rollout And Recovery

The action intentionally fails rather than falling back to the runner default.
If GitHub removes Xcode 26.5 from `macos-26`, update the version, verification
prefix, runner image, and cache namespace together, then rerun all affected
workflows. Do not reuse caches across compiler baselines.
