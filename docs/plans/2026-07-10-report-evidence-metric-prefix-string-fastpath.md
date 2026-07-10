# Report evidence metric-prefix string fast path slice

## Scope

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._rule_matches_report()` metric-prefix matching.
Metric rows normally provide `metric` as an exact string, but the previous loop still called `str()` for every metric before checking the prefix initials and tuple.

## Registered probe

The affected path is already covered by the registered PR-scoped performance probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and reports `metric_prefix_elapsed_ms_mean` alongside aggregate report-evidence metrics.

## Optimization plan

1. Add an exact-string fast path in the metric-prefix loop so common string metrics reuse the existing value directly.
2. Preserve non-string metric semantics by falling back to `str(value)` before prefix checks.
3. Run the registered focused tests, changed-scope coverage, and the registered probe locally on Linux before opening the PR.
4. Use GitHub Actions PR-scoped performance as the registered probe merge gate.

## Verification

- Focused report-evidence gate tests pass.
- Changed-scope coverage for the touched Python file, test file, probe script, and this plan is at least 95%.
- Local registered probe reports stable or improved `metric_prefix_elapsed_ms_mean`; CI remains the source of truth for PR-scoped performance validation.
