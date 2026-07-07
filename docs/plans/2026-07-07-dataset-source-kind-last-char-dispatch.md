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
