# Startup Version Part Parser Binding Slice

## Scope

This Python-only performance slice is limited to `worker.productization.startup_signals.compare_versions()`.
The function already streams normalized version parts without materializing lists; this slice keeps that
behavior and binds the normalized-part parser once before the comparison loop so repeated non-equivalent
version comparisons avoid repeated global lookups.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`startup-signals-version-compare-single-pass` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/startup_signals_version_probe.py`

## Verification plan

Run the registered focused tests, changed-scope coverage command, and local registered probe on Linux before
opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.

## Expected metrics

The primary metric is `elapsed_ms_mean` from `scripts/startup_signals_version_probe.py` and should move lower
or remain within the probe threshold. `peak_bytes_mean`, `comparison_total`, and the update-result allocation
metrics should remain behavior/parity guards.

## Linux boundary

This is pure Python worker/productization code and is locally verifiable on Linux. No Swift runtime effect is
claimed for this slice.
