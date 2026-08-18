# Startup Log Excerpt Handle Local Bindings

## Scope

This Python-only performance slice is limited to startup failure log excerpt tail
scanning in `services/mlx-worker-python/worker/productization/startup_signals.py`.

The log-tail scanner keeps behavior unchanged while binding the file handle
`seek`/`read` methods and the right-strip helper once per `_seek_last_nonempty_line_bounds(...)`
call. This avoids repeated attribute/global lookups inside the reverse chunk scan used by
startup failure classification.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`startup-signals-lazy-worker-log-excerpts` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/startup_signals_log_probe.py`

## Verification Plan

Run the registered focused tests, changed-scope coverage command, `git diff --check`,
and the registered `startup-signals-lazy-worker-log-excerpts` probe locally on Linux.
GitHub Actions PR-scoped performance remains the merge gate for the registered probe
report.
