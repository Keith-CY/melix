# Report evidence metric string fast path

This Python-only performance slice is limited to metric-prefix release-matrix matching in `worker.productization.report_evidence_gate._rule_matches_report()`.

The affected path is covered by the registered PR-scoped performance probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries and reports `metric_prefix_elapsed_ms_mean` plus the aggregate report-evidence gate timings.

## Slice

Metric rows in generated report-evidence payloads normally carry string metric names. The previous loop always wrapped each row value with `str(...)`, preserving support for non-string metric values but paying an avoidable conversion cost on the common string path. This slice keeps the non-string fallback while using the exact string value directly when `type(metric_value) is str`, and binds the prefix-index lookup once for the scan.

## Verification

1. Run the focused metric-prefix behavior tests, including the non-string compatibility case.
2. Run the registered probe tests and changed-scope coverage command from `report-evidence-gate-run-kind-set-membership`.
3. Run the registered PR-scoped performance probe locally on Linux against `origin/main` and this branch via `scripts/pr_scoped_performance_run.py`.
4. Use GitHub Actions PR-scoped performance as the merge gate after opening the PR.
