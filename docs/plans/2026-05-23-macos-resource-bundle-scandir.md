# macOS App Resource Bundle Scandir Slice

## Goal

Reduce filesystem enumeration overhead while packaging SwiftPM resource bundles into the macOS app bundle.

## Scope

- `services/mlx-worker-python/worker/productization/macos_app_bundle.py`
- `services/mlx-worker-python/tests/test_macos_app_bundle.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Registered Probe

This slice registers `macos-app-resource-bundle-scandir` in `infra/perf/pr_scoped_probes.json`. The entry includes focused `test_command`, `coverage_command`, and `probe_command` fields and runs on `ubuntu-latest`.

The probe creates a synthetic SwiftPM build-products directory with many `.bundle` directories plus non-bundle entries, monkeypatches `copytree` to isolate enumeration overhead, and records `elapsed_ms_mean`, `elapsed_ms_min`, and `copied_count`.

## Implementation Plan

1. Add regression coverage proving `_copy_swiftpm_resource_bundles(...)` does not call `Path.glob("*.bundle")` and preserves lexicographic copy order.
2. Replace `sorted(source_root.glob("*.bundle"))` with `os.scandir(...)`, directory filtering, and a sorted bundle-name list.
3. Register the PR-scoped probe and add a probe-selection regression test.
4. Run the focused tests, changed-scope coverage, and registered probe locally on Linux.
5. Use PR-scoped performance CI as the final registered probe gate before merge.

## Metrics

Primary metric: `macos-app-resource-bundle-scandir` `elapsed_ms_mean` (lower is better). Secondary metric: `elapsed_ms_min` (lower is better). `copied_count` must remain equal to the synthetic bundle count.

## Validation Boundary

This is a Python packaging-path slice. Local Linux validation covers the Python behavior and registered probe. It does not validate Swift runtime behavior.
