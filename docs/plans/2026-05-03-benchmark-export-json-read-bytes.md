# Benchmark Export JSON Read-Bytes Slice

## Summary

This performance slice keeps benchmark export artifact collection behavior unchanged while reducing per-file overhead for small JSON artifact reads.

## Scope

- Affected path: `services/mlx-worker-python/worker/productization/benchmark_export.py`
- Registered PR-scoped probe: `benchmark-export-run-scan-single-pass`
- Supporting tests: `services/mlx-worker-python/tests/test_benchmark_export.py`

## Optimization

`_load_json_object` now reads JSON artifacts with `Path.read_bytes()` and parses the bytes payload with `json.loads()`. This avoids constructing a text file wrapper for each small JSON artifact while preserving object-type validation and error behavior for missing or invalid files.

## Validation Plan

Run the registered probe's focused tests, changed-scope coverage command, and probe command locally on Linux before opening the PR. The CI PR-scoped performance workflow remains the merge gate for registered probe validation.

## Metrics

Primary registered metrics from `benchmark-export-run-scan-single-pass`:

- `elapsed_ms_mean` lower is better
- `per_run_ms_mean` lower is better
- `csv_elapsed_ms_mean` lower is better
