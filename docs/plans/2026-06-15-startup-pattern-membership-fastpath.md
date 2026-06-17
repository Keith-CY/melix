# Startup Pattern Membership Fast Path

This Python performance slice keeps startup failure classification behavior unchanged while reducing fixed-pattern membership overhead in `services/mlx-worker-python/worker/productization/startup_signals.py`.

The affected path is covered by the registered PR-scoped probe `startup-signals-lazy-worker-log-excerpts` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for the startup signals implementation, tests, probe script, and PR-scoped registry coverage.

## Scope

- Add direct fixed-pattern checks for the startup port-conflict and crash pattern tuples.
- Preserve the generic tuple scan fallback for any future non-standard pattern tuple.
- Keep the slice Python-only and locally verifiable on Linux.

## Validation

Run the focused startup-signals tests, changed-scope coverage, and the registered `startup-signals-lazy-worker-log-excerpts` probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate.
