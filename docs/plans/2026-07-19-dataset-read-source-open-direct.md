# Dataset Source Reader Direct Binary Open

## Scope

This Python-only performance slice is limited to `_read_source_text(...)` in
`services/mlx-worker-python/worker/productization/dataset_preparation.py`.

Dataset ingest reads every accepted source file before normalizing and segmenting
records. The source path is already a `Path`, but the hot reader does not need
`Path.open()` wrapper dispatch for either unbounded or capped reads. This slice
converts the path once with `os.fspath(...)` and uses direct binary `open(...)`
for both branches while preserving UTF-8 decoding, cap enforcement, and the
single-read unbounded behavior.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The
registry entry already includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_source_records_probe.py`

This slice extends `scripts/dataset_source_records_probe.py` with
`read_elapsed_ms_*` metrics so the registered probe directly measures the source
reader in addition to traversal, classification, and record materialization.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, `git diff --check`,
and the registered `dataset-source-records-scandir` probe locally on Linux before
opening the PR. GitHub Actions PR-scoped performance remains the merge gate for
the registered probe report.
