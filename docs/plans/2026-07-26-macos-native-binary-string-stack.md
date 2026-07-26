# macOS Native Binary Candidate String Stack

## Scope

This Python performance slice is limited to `_iter_python_native_binary_candidates()` in `services/mlx-worker-python/worker/productization/macos_app_bundle.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `macos-app-native-binary-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry watches the macOS app bundle helper, focused bundle tests, PR-scoped performance tests, and the registry itself, and includes focused `test_command`, `coverage_command`, and `probe_command` entries.

## Slice

1. Keep the existing `os.scandir()` depth-first traversal and candidate selection semantics.
2. Store pending directories as filesystem strings on the traversal stack so the hot scan avoids allocating `Path` objects for directories that are only used for traversal, and use a direct `/bin` suffix check for runtime executable eligibility instead of reconstructing directory `Path` objects.
3. Construct `Path` objects only for selected native-binary or runtime-executable candidates returned to callers.
4. Add a regression assertion that candidate scanning does not construct `Path` objects for directory stack entries.

## Metrics

Expected metrics are lower `elapsed_ms_mean` and `elapsed_ms_min` in the registered `macos-app-native-binary-scandir` probe. `candidate_count` should remain unchanged.
