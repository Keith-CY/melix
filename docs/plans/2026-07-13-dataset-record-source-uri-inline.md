# Dataset Record Source URI Inline Access

## Scope

This Python-only performance slice is limited to dataset ingest record assembly in
`services/mlx-worker-python/worker/productization/dataset_preparation.py`.

The hot `_record()` helper now writes `path.name` directly into the emitted
record instead of first storing the source URI in a short-lived local variable.
The source-id, source URI, metadata-copying, normalized-text, digest, and byte
accounting contracts remain unchanged.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The entry
includes focused `test_command`, `coverage_command`, and `probe_command` values
for the dataset preparation ingest tests and `scripts/dataset_source_records_probe.py`.

The probe reports record assembly timing through `record_elapsed_ms_mean`,
`record_elapsed_ms_min`, and `record_elapsed_ms_p95`, alongside traversal and
source-kind classification metrics.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, `git diff --check`,
and the registered `dataset-source-records-scandir` probe locally on Linux before
opening the PR. GitHub Actions PR-scoped performance remains the merge gate for
the registered probe report.
