# Dataset source size stat local binding

## Scope

This Python-only performance slice is limited to `services/mlx-worker-python/worker/productization/dataset_preparation.py` and the dataset ingest source-size accounting path that runs after source file discovery.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for `dataset_preparation.py`, `test_dataset_preparation_ingest.py`, `test_pr_scoped_performance.py`, and `scripts/dataset_source_records_probe.py`.

## Optimization

`_source_size_entries(...)` previously performed an `entries.append` lookup and a bound `path.stat` lookup for every discovered source path. This slice binds `entries.append` and `Path.stat` once per helper invocation, preserving the existing ordered `(Path, size)` output, test monkeypatch seam, and missing-file fallback while reducing repeated Python attribute lookups in large source trees.

## Validation Plan

1. Keep the regression coverage for ordered source-size accounting, including a missing file fallback.
2. Run the registered focused test command for `dataset-source-records-scandir` locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run the registered local probe on Linux and compare against the synced `origin/main` baseline.
5. Use the PR-scoped performance GitHub Actions report as the merge gate.
