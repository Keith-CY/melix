# macOS app native binary candidate name fast path

## Context

The macOS app bundle productization helper walks the packaged Python runtime and
site-packages trees to collect native binary candidates for stripping. The
registered PR-scoped probe `macos-app-native-binary-scandir` covers
`services/mlx-worker-python/worker/productization/macos_app_bundle.py` and
measures this traversal over a synthetic runtime/site-packages tree.

## Slice

This slice keeps the existing traversal order and candidate semantics while
removing per-entry `os.path.splitext()` plus parent-directory path parsing from
`_iter_python_native_binary_candidates()`. The traversal now checks native binary
suffixes directly against `entry.name` and computes whether the current scanned
directory is `bin` once per directory.

## Verification

- Focused tests: the `macos-app-native-binary-scandir` registered test command.
- Coverage: the registered changed-scope coverage command for the same probe.
- Metrics: the registered `macos-app-native-binary-scandir` probe, run locally on
  Linux and again in PR-scoped performance CI.

## Boundaries

This is a Python packaging-path optimization and is locally verifiable on Linux.
It does not change Swift runtime behavior or generated protocol artifacts.
