# Startup Signals Lazy Worker Log Probe Plan

## Goal

Reduce redundant startup-failure log work in `classify_startup_failure(...)` by avoiding worker log reads when the control-plane signal already proves a host-port conflict or control-plane crash, and by avoiding all log reads when the captured startup error text already contains a host-port conflict signature.

## Linux-only constraint

This slice is Python-only and can be verified on Linux with focused pytest, changed-scope coverage, and a synthetic performance probe.

## Touched files

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `scripts/startup_signals_log_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Performance probe definition

Register `startup-signals-lazy-worker-log-excerpts` in PR-scoped performance CI. The probe runs `scripts/startup_signals_log_probe.py`, which builds synthetic control-plane and worker log files, repeatedly classifies three startup failure cases, and reports elapsed time plus log-read counts.

## Success metrics

- Host-port conflict cases proven directly by `error_text` should read no logs (`conflict_log_reads_mean=0.0`).
- Host-port conflict and control-plane crash cases proven from control-plane logs should read only the control-plane log (`*_log_reads_mean=1.0`) instead of also reading worker logs.
- Worker-crash classification must still inspect worker logs and preserve classification behavior.
- Changed-scope automated coverage must be at least 95%.
