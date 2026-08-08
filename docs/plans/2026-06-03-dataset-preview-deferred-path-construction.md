# Dataset preview deferred path construction

## Scope

This Python performance slice is limited to the dataset registry first-preview and limited-preview scan path in `services/mlx-worker-python/worker/dataset_registry/catalog.py`.

## Motivation

`read_hf_dataset_snapshot_rows(..., limit=1)` uses `_first_supported_dataset_file(...)` to find the first readable dataset file without materializing the full snapshot file list. `_next_supported_scan_entry(...)` previously constructed a `Path` object every time a better lexical candidate was found while scanning a directory. Snapshots with many ignored sidecar files before the first data file can therefore spend extra allocations on candidates that are discarded within the same scan.

For multi-row previews, `_iter_limited_preview_dataset_files(...)` repeatedly walks the limited-preview scan loop and may recurse into the first dataset directory. Keeping the hot scan helper and recursive generator in local bindings avoids repeated global lookups while preserving the existing lexical ordering and no-full-tree-sort behavior.

## Probe coverage

The affected path is covered by the registered PR-scoped performance probe `dataset-registry-preview-limit-short-circuit` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values. This slice keeps the same probe; the synthetic snapshot includes ignored sidecar files and a multi-limit preview case so both first-preview and limited-preview scan paths are represented. Because `catalog.py` is also watched by the split-match dataset probe, this slice extends that probe's focused commands with the limited-preview regression test so all selected PR-scoped probes cover the changed lines.

## Plan

1. Preserve the existing regression coverage that proves limited previews do not fall back to a full sorted walk and avoid constructing discarded sibling paths.
2. Store the winning raw entry path during first-preview scans and construct a single `Path` only for the final selected entry.
3. Bind the limited-preview scan helper and recursive generator locally inside `_iter_limited_preview_dataset_files(...)` so repeated scan batches avoid global lookups.
4. Run focused pytest, changed-scope coverage, and the registered probe locally on Linux.

## Success criteria

- Focused dataset registry and PR-scoped performance tests pass.
- Changed-scope coverage for the touched files is at least 95%.
- The registered `dataset-registry-preview-limit-short-circuit` probe reports lower preview elapsed time or a clearly bounded allocation-path improvement.
- PR-scoped performance CI completes successfully before merge.
