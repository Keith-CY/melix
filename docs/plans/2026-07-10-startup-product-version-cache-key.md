# Startup product version cache key slice

## Scope

This Python-only performance slice is limited to `worker.productization.startup_signals.read_product_version()`.

The hot repeated-read path already caches the resolved `pyproject.toml` `Path` and uses a stat-valid version cache. This slice keeps that behavior but also caches the string cache key derived from the resolved `pyproject.toml` path so repeated stat-valid reads avoid reconstructing the same path string before the version-cache lookup.

## Registered performance probe

The affected path is covered by the registered PR-scoped performance probe `startup-signals-version-compare-single-pass` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and reports:

- `product_version_elapsed_ms_mean` for repeated cached product version reads.
- `product_version_peak_bytes_mean` for allocation stability.
- update-check and version-comparison metrics to guard adjacent startup-signal paths.

## Verification plan

Run the registered focused startup-signals tests, changed-scope coverage, and the registered probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate after the PR is opened.
