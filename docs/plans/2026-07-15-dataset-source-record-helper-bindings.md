# Dataset Source Record Helper Bindings Performance Slice

## Context

The registered PR-scoped probe `dataset-source-records-scandir` covers
`services/mlx-worker-python/worker/productization/dataset_preparation.py`,
including dataset ingest source-file traversal, source-kind classification, and
record assembly. The source-record loop calls the same module-level helpers for
every candidate file while building records from already enumerated source paths.

## Slice

Bind the source-record loop helpers (`_source_kind`, `_read_source_text`,
`_structured_records`, `_normalize_line_endings`, `_metadata_for_path`, `_record`)
and `operator_failures.append` once before iterating. This keeps the same source
path order, unsupported/empty-source failure payloads, structured-data handling,
line-ending normalization, metadata, and record schema while avoiding repeated
global or attribute lookups inside the per-file loop.

This slice does not change directory traversal, privacy detection, segmentation,
deduplication, upload caps, or dataset versioning behavior.

## Probe

Registered probe: `dataset-source-records-scandir`

The registry entry in `infra/perf/pr_scoped_probes.json` includes focused
`test_command`, `coverage_command`, and `probe_command` entries for the affected
path and `scripts/dataset_source_records_probe.py`.

## Verification Plan

1. Run the registered focused test command for `dataset-source-records-scandir`.
2. Run the registered changed-scope coverage command for the same probe.
3. Run the registered probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the final merge gate for the
   registered probe report.

## Expected Impact

The primary expected metric is lower or stable `record_elapsed_ms_mean` in the
registered dataset source-record workload. Overall `elapsed_ms_*` may be stable
because the workload still includes filesystem traversal and file reads.
