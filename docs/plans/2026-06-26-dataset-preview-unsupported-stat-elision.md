# Dataset Preview Unsupported File Stat Elision

## Scope

This Python-only performance slice is limited to the dataset preview scan helpers in `services/mlx-worker-python/worker/dataset_registry/catalog.py`.

The affected path is covered by the registered PR-scoped probe `dataset-registry-preview-limit-short-circuit` in `infra/perf/pr_scoped_probes.json`. That registry entry has focused `test_command`, `coverage_command`, and `probe_command` entries and watches the dataset registry implementation, tests, and preview probe script.

## Plan

1. Preserve sorted depth-first preview behavior for supported dataset files and directories.
2. Avoid the extra `DirEntry.is_file()` call for README and unsupported regular-file names after the directory check proves the entry is not a directory.
3. Add a focused regression test that unsupported names do not require file-stat classification while directories with unsupported-looking names still remain traversable.
4. Run the registered focused tests, changed-scope coverage, and `dataset_registry_preview_limit_probe.py` locally on Linux.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Metrics

Primary metric: `elapsed_ms_mean` from `dataset-registry-preview-limit-short-circuit`.
Secondary metrics: `multi_limit_elapsed_ms_mean`, `peak_bytes_mean`, and the existing zero-limit/no-rescan counters from the same probe.
