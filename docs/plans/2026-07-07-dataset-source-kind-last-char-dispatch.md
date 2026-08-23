# Dataset Source Kind Last-Character Dispatch

## Scope

This Python-only performance slice is limited to dataset ingest source-kind
classification in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.

The hot helper `_classify_source_kind_name()` now dispatches common lowercase
suffix checks by the final filename character before evaluating suffix-specific
slices. This preserves the existing fallback path for uppercase or uncommon
suffix spellings while avoiding most repeated slice comparisons on the common
lowercase dataset source names used by ingest scans.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_source_records_probe.py`

The probe reports source-tree traversal timing plus source-kind classification
metrics (`source_kind_elapsed_ms_mean`, `source_kind_elapsed_ms_min`, and
`source_kind_elapsed_ms_p95`).

## Verification Plan

Run the registered focused tests, changed-scope coverage command, `git diff --check`,
and the registered `dataset-source-records-scandir` probe locally on Linux before
opening the PR. GitHub Actions PR-scoped performance remains the merge gate for
the registered probe report.

## 2026-08-23 Follow-up: Metadata Helper Elision

This follow-up stays within the same dataset source-record ingestion hot path.
`_iter_source_records()` only needs path metadata for code sources because
`_metadata_for_path()` currently contributes the language metadata derived from
the file suffix. Text, markdown, PDF/DOCX text, and other non-code records keep
empty metadata, so they can bypass the metadata helper during the per-source
record loop while preserving the existing record payload.

The same registered PR-scoped probe, `dataset-source-records-scandir`, remains
the required validation source. Its local Linux probe output includes the
`record_elapsed_ms_*` and `inventory_elapsed_ms_*` metrics that cover the record
construction path affected by this slice, while GitHub Actions PR-scoped
performance remains the merge gate.

## 2026-08-23 Follow-up: Empty Inventory Metadata Update Elision

This follow-up remains inside the dataset source-record ingestion hot path and
targets `_source_inventory()`. The inventory aggregation loop receives one
record per simple source file before structured-row expansions are added. Most
simple text, markdown, and code records carry empty metadata, while structured
row records carry `row_index` metadata. The loop now skips the per-record
`dict.update({})` call for empty metadata and only merges non-empty metadata,
preserving the resulting inventory payload while reducing work during large
source-tree scans.

The registered `dataset-source-records-scandir` probe remains the required
validation source. Its `inventory_elapsed_ms_*` metrics exercise the affected
aggregation path locally on Linux and in the PR-scoped CI performance workflow.
