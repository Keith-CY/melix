# Startup Log Exists Check Elision

## Goal

Reduce redundant filesystem work in startup failure classification by avoiding a separate `Path.exists()` probe before reading log excerpts.

## Scope

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/startup_signals_log_probe.py`

## Linux Verification Path

This is a Python-only slice and can be verified on Linux with focused pytest, changed-scope coverage, and the existing `startup-signals-lazy-worker-log-excerpts` PR-scoped performance probe.

## Performance Probe

Use `scripts/startup_signals_log_probe.py` and the registered `startup-signals-lazy-worker-log-excerpts` probe. The local structural metric is `*_log_path_exists_checks_mean`; success means startup classification no longer calls `Path.exists()` while preserving log-read counts and classifications.

## Success Metrics

- Focused startup-signal tests pass.
- Changed-scope automated coverage is at least 95%.
- Local probe reports `control_crash_log_path_exists_checks_mean=0.0` and `worker_crash_log_path_exists_checks_mean=0.0` on the optimized branch.
- Existing log-read metrics remain unchanged (`control_crash_log_reads_mean=1.0`, `worker_crash_log_reads_mean=1.0`).
