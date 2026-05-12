# Runtime Utils Top-Level Weight DirEntry Slice

## Goal

Reduce top-level model weight byte-estimation overhead for flat model bundles with many files by avoiding per-entry `Path` allocation and redundant `Path.is_file()`/`Path.stat()` calls.

## Linux Verification Scope

This is a Python runtime utility slice and is locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe.

## Touched Files

- `services/mlx-worker-python/worker/runtime/runtime_utils.py`
- `services/mlx-worker-python/tests/test_runtime_utils.py`
- `docs/plans/2026-05-12-runtime-utils-top-level-weight-direntry.md`

## Registered Probe

The affected path is covered by the registered `runtime-utils-top-level-weight-streaming` probe in `infra/perf/pr_scoped_probes.json`:

- `watch_globs` includes `services/mlx-worker-python/worker/runtime/runtime_utils.py`, focused runtime utility tests, and `scripts/runtime_utils_top_level_weights_probe.py`.
- `test_command` runs the focused model weight byte-estimation tests and PR-scoped performance dispatch checks.
- `coverage_command` measures changed-scope coverage for runtime utilities, focused tests, PR-scoped performance dispatch, and the probe script.
- `probe_command` builds a synthetic flat model bundle with thousands of top-level files and repeatedly calls `estimate_model_weight_resident_bytes(...)`, reporting elapsed time and peak memory.

## Optimization Slice

Replace the fallback top-level `Path.iterdir()` scan with an `os.scandir()` pass that uses `DirEntry.name`, `DirEntry.is_file()`, and `DirEntry.stat()` directly. This preserves the existing top-level-only semantics while avoiding `Path` object allocation and extra path method dispatch for each directory entry.

## Success Metrics

- Functional behavior remains unchanged for indexed bundles, flat bundles, malformed indexes, missing paths, and stat/listing errors.
- Changed-scope coverage remains at least 95%.
- The registered `runtime-utils-top-level-weight-streaming` probe should show lower `elapsed_ms_mean` and/or lower `peak_bytes_mean` versus the `origin/main` baseline.

## Verification Commands

- Registered focused `test_command` from `infra/perf/pr_scoped_probes.json`.
- Registered `coverage_command` from `infra/perf/pr_scoped_probes.json`.
- Registered `probe_command` from `infra/perf/pr_scoped_probes.json`, run locally against `origin/main` and this branch.
- `git diff --check`.
