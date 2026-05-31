# Closure Audit Severity Metrics Single Pass

## Scope

This Python performance slice is limited to `services/mlx-worker-python/worker/productization/closure_audit.py`.
It keeps closure-audit report behavior unchanged while computing severity metrics and unresolved finding summaries in one pass over the already ordered findings.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `closure-audit-probe-source-short-circuit` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries that exercise closure-audit behavior and report `elapsed_ms_mean`, `peak_bytes_mean`, and `probe_file_reads_mean`.

## Implementation Plan

1. Add a focused regression test for the severity-metric helper so count and unresolved-summary parity is explicit.
2. Replace the four repeated severity scans plus separate unresolved scan with a single loop over `ordered_findings`.
3. Run the registered focused test command, changed-scope coverage command, and local registered probe on Linux.
4. Use GitHub Actions and the registered PR-scoped performance report as the merge gate before squash merging.

## Metrics

Local Linux verification will compare the registered probe against an `origin/main` baseline using `scripts/pr_scoped_performance_run.py`.
