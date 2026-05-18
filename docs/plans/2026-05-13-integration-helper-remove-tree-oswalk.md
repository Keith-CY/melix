# Integration Helper Remove-Tree Streaming Cleanup Slice

## Context

`tests/integration/helpers.py` owns cleanup for temporary Melix runtime state used by
integration fixtures. The prior cleanup path materialized every descendant with
`Path.rglob("*")` and sorted the full list before deletion. Large runtime-state
trees can therefore pay an avoidable allocation and sort cost during teardown.

## Scope

This slice only changes `LiveMelixStack._remove_tree` to delete fixture-owned
runtime trees with `os.walk(..., topdown=False, followlinks=False)`. The helper
keeps the same externally visible behavior: files and symlinks are unlinked,
directories are removed after their children, missing roots are tolerated, and
directory symlink targets are not followed.

## Probe and Metrics

The existing PR-scoped integration-helper probe
`integration-swift-binary-resolution-scandir` is extended so changes to
`tests/integration/helpers.py` run focused tests, changed-scope coverage, and a
registered command-json probe for cleanup performance.

The cleanup probe reports:

- `remove_tree_elapsed_ms_mean`
- `remove_tree_legacy_elapsed_ms_mean`
- `remove_tree_delta_ms_mean`
- `remove_tree_peak_bytes_mean`
- `remove_tree_legacy_peak_bytes_mean`
- `remove_tree_peak_bytes_delta_mean`
- fixture dimensions (`remove_tree_directories`, `remove_tree_files_per_directory`)

The delta metrics are improvement margins relative to the legacy cleanup path,
so the registered PR-scoped thresholds include small absolute tolerances for
timing and allocation jitter. Direct elapsed-time regressions still block
through `remove_tree_elapsed_ms_mean`.

Success means behavior parity tests pass and the registered probe shows lower
mean elapsed time or lower peak memory for the os.walk cleanup path.
