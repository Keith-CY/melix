# Dataset preview scandir local bindings

## Scope

This Python-only performance slice is limited to the dataset registry limit-one preview scan in `services/mlx-worker-python/worker/dataset_registry/catalog.py`, specifically `_next_supported_scan_entry(...)`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `dataset-registry-preview-limit-short-circuit` in `infra/perf/pr_scoped_probes.json`. The registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries for the dataset registry preview path.

## Optimization

The limit-one preview scan repeatedly calls `_next_supported_scan_entry(...)` while selecting the first supported preview file without sorting the full tree. This slice keeps the existing error-handling and depth-first ordering semantics intact, including the current behavior that an `is_dir(follow_symlinks=False)` error skips an entry before any file check.

Within that semantic boundary, `_next_supported_scan_entry(...)` now binds `os.scandir` and `os.fspath` to local names before entering the scan loop. This avoids repeated module attribute lookups on each call to the hot helper while preserving the same scan order and OSError handling.

A broader file-first stat-order attempt was rejected because the existing regression suite proves `_next_supported_scan_entry(...)` must skip entries whose directory stat raises, even if a later file stat would succeed.

## Verification plan

1. Run the registered focused tests for `dataset-registry-preview-limit-short-circuit`.
2. Run the registered changed-scope coverage command for the same probe.
3. Run the registered local probe on Linux and compare against the pre-change baseline.
4. Use GitHub Actions PR-scoped performance as the final merge gate.

## Expected performance signal

Expected signal: a small reduction in `elapsed_ms_mean` and `multi_limit_elapsed_ms_mean` from avoiding module attribute lookups for each preview scan helper invocation. `zero_limit_elapsed_ms_mean` is not expected to materially change.
