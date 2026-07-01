# Trajectory manifest string-path open performance slice

This Python-only performance slice is limited to `worker.trajectory_provenance.load_trajectory_provenance_from_snapshot_manifest()` when callers pass a plain string manifest path.

## Scope

- Keep trajectory manifest provenance extraction behavior unchanged.
- For exact `str` manifest paths, avoid constructing a temporary `Path` object solely to call `Path.read_bytes()`; read bytes through direct binary `open()` and reuse the original string as the snapshot manifest path text.
- Preserve the existing `Path` and path-like behavior, including the registered byte-loading path for `Path` callers.
- Extend the registered `trajectory-manifest-json-load` probe to measure the string-path fast path.

## Registered performance probe

The affected path is already covered by `trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json` with focused `test_command`, `coverage_command`, and `probe_command` entries. This slice adds a focused unit test for the string-path branch and updates the probe workload to pass a string manifest path to the optimized implementation.

Metrics:

- `new_mean_ms` / `elapsed_ms_mean`: lower is better.
- `delta_ms` and `speedup`: informational comparison against the baseline loader.
- `new_peak_bytes_mean`: lower is better.

## Verification plan

Run locally on Linux before pushing:

1. Registered focused tests for `trajectory-manifest-json-load`.
2. Registered changed-scope coverage command for `worker.trajectory_provenance`.
3. Registered probe command for `trajectory-manifest-json-load`.
4. `git diff --check`.

GitHub Actions PR-scoped performance remains the merge gate after opening the PR.
