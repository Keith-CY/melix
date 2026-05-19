# Startup log excerpt single-pass combine

## Context

This Python-only performance slice is limited to startup failure log excerpt assembly in `services/mlx-worker-python/worker/productization/startup_signals.py`.

The affected path is covered by the registered PR-scoped performance probe `startup-signals-lazy-worker-log-excerpts` in `infra/perf/pr_scoped_probes.json`. That probe has focused `test_command`, `coverage_command`, and `probe_command` entries and measures classification elapsed time plus log-read counts for the startup signal paths.

## Slice

Avoid allocating a temporary excerpt list and avoid the final `" | ".join(...)` call for the common one-log startup failure cases. `_log_excerpt()` now combines excerpts as it scans paths, preserving order and the same delimiter for multi-log diagnostics.

## Behavior constraints

- Preserve missing-log handling: no `Path.exists()` preflight; rely on read errors.
- Preserve empty-log skipping.
- Preserve multi-log order and delimiter: `control | worker`.
- Preserve startup failure classification and report fields.

## Verification plan

Run the focused startup-signals test set, changed-scope coverage, and the registered `startup-signals-lazy-worker-log-excerpts` probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate.
