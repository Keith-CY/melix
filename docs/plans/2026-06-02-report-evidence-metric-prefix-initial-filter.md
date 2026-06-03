# Report Evidence Metric Prefix Initial Filter

## Scope

This Python-only performance slice is limited to
`worker.productization.report_evidence_gate._rule_matches_report()` metric-prefix
matching. Behavior remains equivalent: a report still matches a metric-prefix
rule when at least one metric string starts with one of the configured prefixes,
including the existing empty-prefix edge case.

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`. That registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for
`report_evidence_gate.py`, the focused report-evidence tests, PR-scoped
performance tests, and `scripts/report_evidence_gate_run_kind_probe.py`.

The probe reports `metric_prefix_elapsed_ms_mean` as part of its aggregate
`elapsed_ms_mean`, so this slice uses that metric as the primary local Linux
signal.

## Plan

1. Add regression coverage for metric-prefix fast rejection and empty-prefix
   behavior.
2. Cache tuple metric-prefix normalization together with first-character metadata.
3. Skip expensive tuple `startswith()` checks when a metric's first character
   cannot match any non-empty configured prefix.
4. Run the focused registered tests, changed-scope coverage, and registered probe
   locally on Linux before opening the PR.
5. Use the GitHub PR-scoped performance workflow as the merge gate.

## Success criteria

- Focused report-evidence tests pass.
- Changed-scope coverage for the touched files is at least 95%.
- The registered local probe reports lower `metric_prefix_elapsed_ms_mean` and
  lower aggregate `elapsed_ms_mean` with unchanged guard-rail counts.
- GitHub Actions, including the PR-scoped performance report, complete
  successfully before merge.
