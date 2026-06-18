# Startup Failure Empty Pattern Scan Skip

## Scope

This performance slice keeps startup failure classification behavior unchanged while
skipping direct substring pattern scans when the direct error text or gathered log
excerpt is empty. The affected code path is
`services/mlx-worker-python/worker/productization/startup_signals.py`.

## Registered Probe

The path is covered by the registered PR-scoped performance probe
`startup-signals-lazy-worker-log-excerpts` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries, and watches the
startup signals implementation, focused tests, probe script, and PR scoped
performance tests.

## Verification Plan

- Add a regression test proving empty direct error/log values do not call the
  pattern matcher.
- Keep existing direct error text, control-plane log, worker log, and hang
  classification tests passing.
- Run the registered focused test command, changed-scope coverage command, and
  registered probe locally on Linux before opening the PR.
- Use the PR-scoped performance workflow as the merge gate for registered probe
  validation.
