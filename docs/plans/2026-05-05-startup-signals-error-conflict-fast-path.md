# Startup Signals Error Conflict Fast Path

## Goal

Reduce unnecessary startup-failure log reads when `classify_startup_failure()` receives a direct port-conflict error from the launching process. The current implementation reads the control-plane log before checking whether `error_text` already contains a host-port-conflict signature.

## Scope

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `scripts/startup_signals_log_probe.py`
- `infra/perf/pr_scoped_probes.json` (registered probe verification only; no registry behavior change expected)

## Linux-only verification path

This is a Python worker/productization helper slice and is locally verifiable on Linux. No Swift runtime effect is claimed.

## Registered performance probe

Use the existing PR-scoped registered probe `startup-signals-lazy-worker-log-excerpts` in `infra/perf/pr_scoped_probes.json`. The probe already includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches the affected startup signals path.

The probe reports:

- `conflict_elapsed_ms_mean` (lower is better)
- `conflict_log_reads_mean` (lower is better; target is zero when `error_text` proves the port conflict)
- `control_crash_elapsed_ms_mean` / `control_crash_log_reads_mean` (regression guard)
- `worker_crash_elapsed_ms_mean` / `worker_crash_log_reads_mean` (regression guard)

## Implementation plan

1. Add a regression test proving an `error_text` port conflict does not read any startup logs and still returns a useful conflict report.
2. Move the direct `error_text` port-conflict classification ahead of control-plane log excerpt reads.
3. Preserve existing control-plane and worker crash behavior for cases where `error_text` alone is not enough to classify the failure.
4. Run focused tests, changed-scope coverage, and the registered probe locally before PR creation.

## Success metrics

- Focused tests pass.
- Changed executable line coverage is at least 95%.
- Local registered probe shows `conflict_log_reads_mean` reduced to `0.0` and no material regression for crash fallback metrics.
- `git diff --check` passes.
