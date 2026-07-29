# Report Evidence Metric Prefix Initial Map

## Summary

This Python-only optimization slice narrows `worker.productization.report_evidence_gate._rule_matches_report` for release-matrix metric-prefix matching.

The matcher already caches tuple metric-prefix normalization on the rule object. This slice extends that cached state with an initial-character map so each metric only checks prefixes that can actually match its first character. Single-prefix buckets are stored as a plain string for `str.startswith`, while multi-prefix buckets keep tuple semantics.

## Scope

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- Registered PR-scoped probe: `report-evidence-gate-run-kind-set-membership`

## Verification Plan

Run the focused report-evidence tests, changed-scope coverage, and the registered probe locally on Linux. The PR-scoped performance workflow remains the merge gate.

## Expected Metrics

The target metric is `metric_prefix_elapsed_ms_mean` from `scripts/report_evidence_gate_run_kind_probe.py`. The direction is lower-is-better; overall probe `elapsed_ms_mean` should not regress.
