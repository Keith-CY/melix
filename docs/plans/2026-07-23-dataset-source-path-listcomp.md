# Dataset source path list comprehension

## Scope

This Python-only performance slice is limited to the dataset preparation source
file discovery hot path in `worker.productization.dataset_preparation`.

The affected path is covered by the registered PR-scoped performance probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for `dataset_preparation.py`, the dataset preparation
regression tests, the PR-scoped performance tests, and
`scripts/dataset_source_records_probe.py`.

## Optimization

After the scandir stack collects and sorts source file path strings, construct
the returned `Path` objects with a list comprehension instead of `list(map(...))`.
The behavior remains identical: recursive discovery still avoids `Path.rglob`,
does not follow directory symlinks, preserves lexical ordering, and returns a
`list[Path]`.

## Verification Plan

1. Run the focused source-path regression and registered probe smoke tests.
2. Run changed-scope coverage for the registered probe scope.
3. Run the registered `dataset-source-records-scandir` probe locally on Linux.
4. Use GitHub Actions and the registered PR-scoped performance workflow as the
   final merge gate.

## Local Metrics Snapshot

Before the implementation on Linux with `MELIX_DATASET_SOURCE_RECORDS_PROBE_SAMPLES=7`:

- `elapsed_ms_mean`: 12.42344211121755
- `elapsed_ms_min`: 11.17237494327128
- `elapsed_ms_p95`: 12.625600909814239
- `file_count_mean`: 7000.0

After the implementation on Linux with the same probe settings:

- `elapsed_ms_mean`: 11.839406265478049
- `elapsed_ms_min`: 11.184084927663207
- `elapsed_ms_p95`: 12.225711019709706
- `file_count_mean`: 7000.0

Local mean delta: `-0.584036 ms` (`1.049330x`, `4.701%` faster). The full
registered local probe with default `sample_count=11` also passed and reported
`elapsed_ms_mean=12.112448457628489`.
