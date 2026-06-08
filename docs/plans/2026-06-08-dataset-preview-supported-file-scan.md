# Dataset preview supported file scan

This Python-only performance slice is limited to the first-file preview path in `services/mlx-worker-python/worker/dataset_registry/catalog.py`.

Registered PR-scoped probe: `dataset-registry-preview-limit-short-circuit` in `infra/perf/pr_scoped_probes.json`. The registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries for this path.

## Root cause

The limit-one preview helper preserves sorted depth-first discovery by repeatedly asking `_next_supported_scan_entry()` for the next candidate. Before this slice, unsupported regular files such as sidecar `.txt` files could become the next best candidate, only to be discarded later by `_first_supported_dataset_file()`. Large snapshots with many unsupported sidecars before the first supported dataset file therefore paid repeated rescans and unnecessary candidate handling.

## Slice

Skip unsupported regular-file suffixes inside `_next_supported_scan_entry()` before recording the best candidate. Directories remain candidates so sorted depth-first traversal is preserved, and README-like files continue to be ignored. Because `_next_supported_scan_entry()` now only returns directories or supported dataset files, `_first_supported_dataset_file()` can return file candidates without rechecking suffixes. The new regression test covers unsupported files that sort before the first data directory, and the registered probe now seeds those prefixed sidecars so CI validates the optimized case.

## Verification plan

- Run the focused dataset-registry preview tests from the registered probe.
- Run changed-scope coverage from the registered probe.
- Run the registered probe locally on Linux and compare against `origin/main` using the same command.
