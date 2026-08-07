# Startup Log Plain Path Fast Path Slice

## Scope

This Python-only performance slice is limited to startup failure log excerpt path handling in `worker.productization.startup_signals._log_excerpt()`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `startup-signals-lazy-worker-log-excerpts` in `infra/perf/pr_scoped_probes.json`.

The probe already includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/startup_signals_log_probe.py`

## Implementation plan

1. Preserve startup failure classification and log excerpt behavior.
2. Avoid `Path.expanduser()` for plain log paths that cannot contain a leading tilde.
3. Keep tilde-prefixed paths on the existing expand-user behavior.
4. Add a focused regression test that fails if plain absolute log paths call `Path.expanduser()`.
5. Verify focused startup-signals tests, changed-scope coverage, and the registered probe locally on Linux.
6. Use the GitHub Actions PR-scoped performance report as the final merge gate.

## Success criteria

- Focused startup-signals tests pass.
- Changed-scope coverage for the touched Python/test/probe scope remains above the repository threshold.
- The registered `startup-signals-lazy-worker-log-excerpts` probe reports stable or improved classification timings without changing log read/path-exists counters.
