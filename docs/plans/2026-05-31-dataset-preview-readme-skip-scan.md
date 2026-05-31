# Dataset preview README skip scan

## Scope

Optimize the Python dataset registry preview path for `limit=1` snapshots that
contain top-level README metadata before the first data directory.

Affected files:

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `docs/plans/2026-05-31-dataset-preview-readme-skip-scan.md`

## Registered probe

Use the existing PR-scoped registered probe
`dataset-registry-preview-limit-short-circuit` in
`infra/perf/pr_scoped_probes.json`. The entry already includes focused
`test_command`, `coverage_command`, and `probe_command` values for this dataset
preview path and watches the dataset registry catalog, focused tests, probe
script, and probe registry.

## Change

The existing `limit=1` preview scanner uses `_next_supported_scan_entry()` to
return lexicographically ordered directory entries. Top-level README metadata is
never a preview data file, but it could still be returned as the current best
file candidate and force `_first_supported_dataset_file()` to rescan the same
directory with `after="README.md"` before reaching the data directory.

This slice skips README metadata files inside `_next_supported_scan_entry()` so
the first preview scan can select the first data directory or data file directly
while preserving README exclusion semantics.

## Verification plan

1. Add a focused regression asserting the helper skips a top-level README and
   selects the data directory without returning README as an intermediate file.
2. Run the registered focused test command for
   `dataset-registry-preview-limit-short-circuit`.
3. Run the registered coverage command and confirm changed-scope coverage stays
   at or above the repository threshold.
4. Run the registered probe locally on Linux and compare against the pre-change
   baseline.

## Local baseline and result

Baseline from `origin/main` with `MELIX_DATASET_PREVIEW_PROBE_SAMPLES=25`:

```json
{"elapsed_ms_mean": 0.310685, "elapsed_ms_min": 0.285174, "file_count": 50000.0, "peak_bytes_mean": 39135.04, "rows_returned": 1.0, "sample_count": 25.0, "zero_limit_elapsed_ms_mean": 0.000605, "zero_limit_peak_bytes_mean": 0.0, "zero_limit_rows_returned": 0.0}
```

Head with the README skip and the same sample count:

```json
{"elapsed_ms_mean": 0.307222, "elapsed_ms_min": 0.276238, "file_count": 50000.0, "peak_bytes_mean": 39130.32, "rows_returned": 1.0, "sample_count": 25.0, "zero_limit_elapsed_ms_mean": 0.000583, "zero_limit_peak_bytes_mean": 0.0, "zero_limit_rows_returned": 0.0}
```

Delta: `elapsed_ms_mean` improved by `0.003463 ms` (`1.011x` speedup),
`elapsed_ms_min` improved by `0.008936 ms`, and `peak_bytes_mean` decreased by
`4.72 bytes`.
