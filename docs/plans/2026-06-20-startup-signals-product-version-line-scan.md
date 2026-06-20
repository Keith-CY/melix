# Startup Signals Product Version Line Scan

## Scope

This Python-only performance slice is limited to `read_product_version(...)` in
`services/mlx-worker-python/worker/productization/startup_signals.py`.

The existing implementation reads the whole `pyproject.toml` into a string and
then runs the compiled version regex over the payload. The startup version probe
already measures the product-version read path, so this slice narrows that path
to a streaming binary line scan while preserving the same accepted version-line
shape.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`startup-signals-version-compare-single-pass` in
`infra/perf/pr_scoped_probes.json`.

The probe has focused `test_command`, `coverage_command`, and `probe_command`
entries, and reports `product_version_elapsed_ms_mean` plus the existing startup
version comparison metrics.

## Implementation Plan

1. Add a regression guard proving `read_product_version(...)` does not rely on a
   full-file `Path.read_text(...)` read.
2. Replace the full-file regex search with a streaming binary line scan for a
   top-level `version = "..."` entry.
3. Keep the accepted syntax equivalent to the prior regex: no leading whitespace,
   optional whitespace around `=`, double-quoted value, and only trailing
   whitespace after the closing quote.
4. Run focused startup-signals tests, changed-scope coverage, and the registered
   local probe on Linux before opening the PR.

## Validation Boundary

This slice only changes Python code and is locally verifiable on Linux. The
registered PR-scoped performance workflow remains the merge gate after push.
