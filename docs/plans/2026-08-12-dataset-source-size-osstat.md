# Dataset Source Size Direct Stat

## Scope

This Python performance slice is limited to dataset ingest source-size accounting
in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.
It preserves source ordering, missing-file fallback size accounting, ingest
receipts, dataset records, and supported source classification.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for source path scanning, source size accounting, source
record materialization, and source-kind classification. This slice extends that
probe with `source_size_elapsed_ms_*` metrics so the stat-loop effect is reported
separately from directory scanning and record materialization noise.

## Slice

`prepare_dataset_ingest(...)` computes `_source_size_entries(...)` for every
source path before materializing source records. The helper previously used the
`Path.stat` descriptor on each `Path` object. This slice binds `os.stat` once and
uses it directly for the same filesystem stat, avoiding the `Path.stat` method
dispatch in the per-source loop while keeping the same `OSError -> size 0`
fallback.

## Verification Plan

1. Add regression coverage that `_source_size_entries(...)` no longer depends on
   `Path.stat` while preserving order and byte sizes.
2. Run the registered focused test command for `dataset-source-records-scandir`.
3. Run changed-scope coverage for the registered probe and require at least 95%
   on the touched scope.
4. Run the registered probe locally on Linux before PR creation; CI PR-scoped
   performance remains the merge gate.

## Boundary

This is a Linux-verified Python slice. No Swift runtime effect is claimed.