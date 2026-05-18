# Startup Version Raw Equality Fast Path

## Scope

This Python-only performance slice targets `worker.productization.startup_signals.compare_versions`.
The existing registered PR-scoped probe `startup-signals-version-compare-single-pass` covers the
changed path through:

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `scripts/startup_signals_version_probe.py`

## Change

Add an exact raw-string equality return before normalization. This preserves existing behavior while
avoiding `strip()` and part parsing for callers that compare the same version string object or the
same exact version text.

The probe workload now includes an exact-equality bucket in addition to differing and `v`-prefix
equivalent pairs so the registered PR-scoped performance workflow measures this fast path directly.

## Verification Plan

Run the registered focused command set on Linux:

1. Focused pytest from the registered probe entry.
2. Registered changed-scope coverage command.
3. Registered command-json probe command.

GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.
