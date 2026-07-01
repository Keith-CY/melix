# Dataset Record Byte Encoding Performance

This Python-only performance slice is limited to dataset source record
materialization in `worker.productization.dataset_preparation._record`.

Registered PR-scoped probe: `dataset-source-records-scandir` in
`infra/perf/pr_scoped_probes.json`. This slice extends the existing probe script
to report `record_elapsed_ms_*` metrics for `_record` materialization in
addition to the existing file traversal and source-kind classification timings.

## Optimization

Encode the normalized record text once and reuse the resulting bytes for both
`content_sha256` and `byte_size`. This preserves record schema and UTF-8 byte
accounting while avoiding a duplicate `str.encode("utf-8")` pass for every
materialized dataset source record.

## Verification Plan

Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux. Accept this slice only if behavior tests pass,
changed-scope coverage remains at or above the repository threshold, and the
registered probe shows a stable `record_elapsed_ms_mean` improvement without
changing file counts, source-kind classification, or record byte accounting.