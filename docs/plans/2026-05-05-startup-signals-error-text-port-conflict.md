# Startup Signals Error-Text Port Conflict Fast Path

## Goal

Reduce redundant startup log reads when `classify_startup_failure(...)` receives an `error_text` payload that already identifies a host-port conflict.

## Linux-only Constraint

This slice is Python-only under `services/mlx-worker-python` and can be validated on Linux with focused pytest, changed-scope coverage, and the existing `startup-signals-lazy-worker-log-excerpts` PR-scoped performance probe.

## Touched Files

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `docs/plans/2026-05-05-startup-signals-error-text-port-conflict.md`

## Performance Probe

Use the existing registered scoped probe:

- `startup-signals-lazy-worker-log-excerpts`

The probe records `conflict_log_reads_mean` and `conflict_elapsed_ms_mean` for the port-conflict path, plus control-plane and worker crash fallback metrics to guard against regressions.

## Success Metrics

- Preserve startup failure classifications and report fields.
- Reduce `conflict_log_reads_mean` from `1.0` to `0.0` when `error_text` contains a port-conflict signal.
- Keep focused tests passing.
- Achieve at least 95% changed-scope automated coverage for touched executable Python scope.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_startup_signals.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_startup_signals_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_startup_signals_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_startup_signals.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_startup_signals_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_startup_signals_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/startup_signals.py services/mlx-worker-python/tests/test_startup_signals.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/startup_signals_log_probe.py

git diff --check
```
