# Dataset source file-path local bindings

## Slice

This Python performance slice is limited to the dataset ingest source-file discovery helper in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.

## Probe coverage

The affected path is covered by the registered PR-scoped probe `dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and reports source file discovery latency plus source-kind classification latency.

## Change

Keep the existing `os.scandir()` traversal semantics, sorted output ordering, non-followed directory symlink handling, and `OSError` skip behavior. Bind hot loop helpers (`append`, `pop`, `os.scandir`, and `Path`) to locals before walking the tree so repeated directory-entry loops avoid repeated attribute lookups.

## Verification

Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux before opening the PR. The PR-scoped performance workflow is the CI validation source for this registered probe.
