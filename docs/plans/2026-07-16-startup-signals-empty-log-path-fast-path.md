# Startup Signals Empty Log Path Fast Path

## Scope

This Python-only performance slice is limited to startup failure classification in
`worker.productization.startup_signals.classify_startup_failure`.

The optimization keeps existing startup-hang behavior for manifests without
control-plane or worker log paths, but returns the hang report before invoking the
log-excerpt helpers. It also binds discovered manifest log-path values once and
reuses those bindings for the control-plane and worker fallback scans.

## Registered Probe

The affected path is already covered by the registered PR-scoped performance
probe `startup-signals-lazy-worker-log-excerpts` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes:

- `test_command` for focused startup-signal behavior and PR-scoped probe tests.
- `coverage_command` for changed-scope coverage over `startup_signals.py`,
  `test_startup_signals.py`, `test_pr_scoped_performance.py`, and
  `scripts/startup_signals_log_probe.py`.
- `probe_command` executing `scripts/startup_signals_log_probe.py` with
  machine-readable metrics for direct conflict/crash, empty-manifest hangs,
  log-backed control/worker crash, tail scanning, and report allocation paths.

## Verification Plan

1. Add a focused regression test proving empty startup manifests skip log-excerpt
   helper calls while preserving `startup_hang` output.
2. Run the registered focused `test_command` locally on Linux.
3. Run the registered changed-scope `coverage_command` locally on Linux.
4. Run the registered `probe_command` locally on Linux and compare against a
   pre-change baseline.
5. Use the GitHub Actions PR-scoped performance report as the merge gate.

## Expected Metrics

The empty-manifest path should improve or remain stable:

- `empty_hang_elapsed_ms_mean`
- `empty_hang_log_reads_mean`
- `empty_hang_log_path_exists_checks_mean`

Log-backed paths should preserve behavior and remain covered by the same
registered probe.
