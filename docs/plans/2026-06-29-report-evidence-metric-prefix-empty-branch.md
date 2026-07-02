# Report Evidence Metric Prefix Empty-Prefix Branch Hoist

## Scope

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._rule_matches_report()` metric-prefix rules.

The affected path is covered by the registered PR-scoped performance probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and runs `scripts/report_evidence_gate_run_kind_probe.py`.

## Optimization

Metric-prefix rules scan report metric rows and compare each metric name against normalized prefix tuples. The previous loop checked `metric_prefix_matches_empty` on every row even though that value is constant for the rule. Empty prefixes intentionally match any metric row, while non-empty prefixes need the first-character and `startswith(...)` checks.

This slice hoists the empty-prefix case before the row loop:

- empty-prefix rules return `bool(metrics)`, preserving the previous "matches any metric row" behavior;
- non-empty prefix rules skip the repeated empty-prefix boolean check inside the hot loop;
- stringification of metric values, first-character filtering, and tuple cache behavior are unchanged.

## Validation

Use the registered probe entry for this path:

- focused report-evidence gate tests from `test_command`;
- changed-scope coverage from `coverage_command`;
- `scripts/report_evidence_gate_run_kind_probe.py` from `probe_command`.

The Linux local probe validates this Python-only slice before PR creation; CI must also run the registered PR-scoped probe before merge.
