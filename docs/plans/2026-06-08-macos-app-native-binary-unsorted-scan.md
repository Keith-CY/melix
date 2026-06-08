# macOS app native binary unsorted scandir slice

## Context

The macOS app bundle productization helper scans packaged Python runtime and
site-packages trees to collect native binary candidates for the stripping step.
The affected path is covered by the registered PR-scoped probe
`macos-app-native-binary-scandir` in `infra/perf/pr_scoped_probes.json`. The
registry entry provides focused `test_command`, `coverage_command`, and
`probe_command` entries for `worker.productization.macos_app_bundle`, its focused
unit tests, and the PR-scoped performance registry checks.

## Slice

This Python-only slice removes the per-directory `sorted(...)` materialization
inside `_iter_python_native_binary_candidates()`. Candidate semantics remain the
same: the helper still uses an explicit `os.scandir()` stack, does not follow
directory symlinks, collects runtime executables only from `bin`, and keeps the
native binary suffix checks on `entry.name`. The stripping step already dedupes
candidate paths before invoking `strip`, so deterministic traversal ordering is
not part of the externally observed result.

## Verification

- Focused tests: run the registered `macos-app-native-binary-scandir`
  `test_command` locally on Linux.
- Coverage: run the registered `coverage_command` and changed-scope coverage
  locally on Linux.
- Metrics: run the registered `probe_command` locally before and after the change
  with repeated samples, then use the PR-scoped performance workflow as the merge
  gate in CI.

## Boundaries

This is a Python packaging-path optimization and is locally verifiable on Linux.
It does not change Swift runtime behavior or generated protocol artifacts.
