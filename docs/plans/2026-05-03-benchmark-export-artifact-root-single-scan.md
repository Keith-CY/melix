# Benchmark Export Artifact-Root Single Scan

## Context

`services/mlx-worker-python/worker/productization/benchmark_export.py` resolves benchmark/evaluation artifact roots before collecting export rows. The current resolver checks direct and fallback roots with separate `Path.is_file()` / `Path.is_dir()` probes for the primary job file, alternate job files, `runs/`, and optional summary file.

This slice keeps the existing export behavior but replaces those repeated path-status probes with one `os.scandir()` pass per candidate root. The slice is Python-only and locally verifiable on Linux.

## Registered Probe

The affected path is already covered by the PR-scoped performance probe `benchmark-export-run-scan-single-pass` in `infra/perf/pr_scoped_probes.json`.

That registered entry includes:

- `test_command` for benchmark export behavior and probe dispatch tests
- `coverage_command` for changed-scope coverage
- `probe_command` for local/CI metrics (`elapsed_ms_mean`, `per_run_ms_mean`, `csv_elapsed_ms_mean`)

No registry shape change is required for this optimization because the touched file is already in the probe's `watch_globs`.

## Slice

- Add a small helper that detects artifact markers from `os.DirEntry` objects.
- Keep direct-root preference over fallback-root behavior unchanged.
- Preserve alternate job filename, optional summary filename, and `runs/` directory marker semantics.
- Add a regression test that fails if artifact-root resolution returns to `Path.is_file()` / `Path.is_dir()` probes.

## Verification

Run the registered focused tests, changed-scope coverage, and local probe on Linux before opening the PR. CI remains the source of truth for the registered PR-scoped probe report after push.
