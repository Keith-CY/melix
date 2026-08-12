# Dataset Registry Unsupported Sidecar Stat Elision Performance Slice

## Status

Candidate for the 2026-08-11 iterative Python performance slice.

## Scope

This Python-only slice is limited to the dataset registry snapshot scanner in
`services/mlx-worker-python/worker/dataset_registry/catalog.py`, specifically
`_iter_supported_dataset_file_stat_records()`.

## Registered Probe

The affected path is already covered by the registered PR-scoped probe
`dataset-registry-snapshot-inference-single-pass` in
`infra/perf/pr_scoped_probes.json`. The probe watches the dataset registry
catalog, focused dataset registry tests, PR-scoped performance tests, and
`scripts/dataset_registry_snapshot_probe.py`; it provides focused
`test_command`, `coverage_command`, and `probe_command` entries.

## Slice

Move scan-time dataset file-format classification before the regular-file stat
call. Unsupported sidecar files such as `.txt` no longer pay the `DirEntry.stat()`
cost before being discarded, while supported dataset files and README metadata
files keep their existing size accounting and relative-path behavior.

## Verification Plan

1. Run the focused regression test proving unsupported files are not statted.
2. Run the registered focused test command and changed-scope coverage command.
3. Run the registered probe command locally on Linux and compare it with the
   pre-change baseline.
4. Let GitHub Actions run the registered PR-scoped performance workflow before
   merge.
