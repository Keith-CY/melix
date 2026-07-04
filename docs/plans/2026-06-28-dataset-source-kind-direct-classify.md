# Dataset Source Kind Direct Classification

## Context

Dataset ingest walks large source trees where filenames are commonly unique. The
registered `dataset-source-records-scandir` PR-scoped probe measures both source
file discovery and source-kind classification latency for
`services/mlx-worker-python/worker/productization/dataset_preparation.py`.

## Slice

Keep the reusable `_source_kind_for_name()` cache helper for callers/tests that
classify repeated basenames, but move the `_source_kind(Path)` ingest hot path to
direct basename classification. This avoids a dictionary lookup/insert for each
unique source filename in large ingest trees while preserving suffix semantics.

## Probe Coverage

The affected path is covered by `dataset-source-records-scandir` in
`infra/perf/pr_scoped_probes.json`. The entry includes focused `test_command`,
`coverage_command`, and `probe_command` values and watches:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_source_records_probe.py`

## Verification Plan

1. Run the registered focused test command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run `scripts/dataset_source_records_probe.py` via the registered probe command
   locally on Linux and compare with a baseline run from `origin/main`.
4. Let PR-scoped performance CI validate the registered probe before merge.

## Expected Result

The `source_kind_elapsed_ms_*` metrics should improve because the unique filename
case no longer fills/probes `_SOURCE_KIND_BY_NAME`. Source file discovery metrics
are expected to remain directionally unchanged.
