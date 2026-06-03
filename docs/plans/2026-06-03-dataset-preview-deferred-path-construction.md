# Dataset preview deferred path construction

## Scope

This Python performance slice is limited to the dataset registry first-preview scan path in `services/mlx-worker-python/worker/dataset_registry/catalog.py`.

## Motivation

`read_hf_dataset_snapshot_rows(..., limit=1)` uses `_first_supported_dataset_file(...)` to find the first readable dataset file without materializing the full snapshot file list. `_next_supported_scan_entry(...)` previously constructed a `Path` object every time a better lexical candidate was found while scanning a directory. Snapshots with many ignored sidecar files before the first data file can therefore spend extra allocations on candidates that are discarded within the same scan.

## Probe coverage

The affected path is covered by the registered PR-scoped performance probe `dataset-registry-preview-limit-short-circuit` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values. This slice keeps the same probe and extends its synthetic snapshot with ignored sidecar files so the scan-candidate allocation path is represented.

## Plan

1. Add regression coverage that counts `Path` construction in `_next_supported_scan_entry(...)` when multiple candidate names are superseded during a first-preview scan.
2. Store the winning raw entry path during the scan and construct a single `Path` only for the final selected entry.
3. Extend `scripts/dataset_registry_preview_limit_probe.py` with configurable ignored sidecar files and report `sidecar_count`.
4. Run focused pytest, changed-scope coverage, and the registered probe locally on Linux.

## Success criteria

- Focused dataset registry and PR-scoped performance tests pass.
- Changed-scope coverage for the touched files is at least 95%.
- The registered `dataset-registry-preview-limit-short-circuit` probe reports lower preview elapsed time or a clearly bounded allocation-path improvement.
- PR-scoped performance CI completes successfully before merge.
