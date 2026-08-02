# macOS Resource Bundle Itemgetter Sort Slice

## Scope

This Python performance slice is limited to `_copy_swiftpm_resource_bundles()` in `services/mlx-worker-python/worker/productization/macos_app_bundle.py`.

The affected path is already covered by the registered PR-scoped probe `macos-app-resource-bundle-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the SwiftPM resource bundle copy path.

## Optimization

The resource bundle scanner builds `(bundle_name, entry.path)` tuples and sorts them for deterministic copy order. This slice replaces the Python lambda key with `operator.itemgetter(0)` so tuple-key extraction uses the C-backed helper while preserving the same bundle ordering and copy semantics.

## Verification Plan

Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate after the PR is opened.

## Local Baseline

Baseline from `origin/main` (`f5c05870`) using the registered probe `macos-app-resource-bundle-scandir`:

- `elapsed_ms_mean=107.925416`
- `elapsed_ms_min=98.066108`
- `bundle_count=900.0`
- `copied_count=900.0`

## Candidate Result

Candidate from `perf/macos-resource-bundle-itemgetter-sort-20260802` using the same registered probe:

- `elapsed_ms_mean=99.809820`
- `elapsed_ms_min=94.196065`
- `bundle_count=900.0`
- `copied_count=900.0`

Delta: `-8.115596 ms` mean (`~7.52%` faster) for the local Linux probe run.
