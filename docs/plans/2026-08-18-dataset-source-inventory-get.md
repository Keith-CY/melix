# Dataset Source Inventory Direct Lookup

## Scope

This Python performance slice is limited to dataset ingest source inventory aggregation in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.

`_source_inventory(...)` receives materialized source records and collapses repeated structured-data rows by `source_uri`. The common structured-source path can include many records for a single JSONL/CSV/TSV source file.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries and watches the dataset ingest implementation, focused tests, probe script, registry, and this plan.

This slice extends `scripts/dataset_source_records_probe.py` with `inventory_elapsed_ms_*` metrics that exercise repeated records per source URI so the aggregation effect is visible separately from directory scanning, source classification, stat accounting, source reads, and record materialization.

## Slice

Replace the hot-loop `dict.setdefault(...)` aggregation with an explicit `get`/insert branch. This avoids constructing an unused default inventory dictionary for every subsequent record from a source URI that is already present, while preserving:

- stable sorted `source_uri` output order;
- first-record `source_id`, `source_kind`, and `content_sha256` retention;
- cumulative `byte_size` and `record_count` accounting;
- cumulative metadata updates for repeated structured records.

## Verification Plan

1. Add regression coverage for repeated structured records sharing a `source_uri`.
2. Run the registered focused test command for `dataset-source-records-scandir`.
3. Run changed-scope coverage for the registered probe and require at least 95% on the touched scope.
4. Run the registered local Linux probe and compare `inventory_elapsed_ms_mean` against `origin/main` before PR creation. CI PR-scoped performance remains the merge gate.

## Follow-up Slice: Direct Metadata Lookup

The 2026-08-23 follow-up keeps the same aggregation behavior and sorted `source_uri` order, but reads `record["metadata"]` directly in the hot loop. `_record(...)` always supplies a `metadata` dictionary for source records, so this preserves the internal record contract while avoiding an optional `.get(...)` method lookup per source record.

The registered `dataset-source-records-scandir` probe remains the measurement gate; its inventory metrics isolate this aggregation/materialization step from source walking and reads.

## Boundary

This is a Linux-verified Python slice. No Swift runtime effect is claimed.
