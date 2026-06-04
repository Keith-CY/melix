# Package macOS build product resolution single scan

## Context

The macOS packaging script resolves Swift build products from direct release/debug
locations first, then from target triple build directories. The registered
PR-scoped probe `package-macos-resolve-fallback-scandir` covers
`scripts/package_macos_menubar_app.py` and measures fallback resolution across a
synthetic `.build` tree with many target triples.

## Slice

This slice keeps the existing resolution order while reusing the target triple
names collected during the first `os.scandir()` pass. When the lexicographically
first triple does not contain the requested product, remaining release/debug
fallbacks no longer rescan the build root.

## Verification

- Focused tests: the package macOS script tests and the registered probe-selection
  tests from `package-macos-resolve-fallback-scandir`.
- Coverage: the registered changed-scope coverage command from
  `package-macos-resolve-fallback-scandir`.
- Metrics: the registered `package-macos-resolve-fallback-scandir` probe, run
  locally on Linux and again in PR-scoped performance CI.

## Boundaries

This is a Python packaging-path optimization and is locally verifiable on Linux.
It does not change Swift runtime behavior or generated protocol artifacts.
