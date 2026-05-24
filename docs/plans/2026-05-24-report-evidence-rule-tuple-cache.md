# Report evidence gate rule tuple cache

This Python-only performance slice keeps report evidence matrix matching semantics unchanged while reducing repeated tuple-to-string normalization in `worker.productization.report_evidence_gate._rule_matches_report(...)`.

## Scope

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/report_evidence_gate_run_kind_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Registered probe

The affected path is covered by registered PR-scoped probe `report-evidence-gate-run-kind-set-membership`. This slice extends that existing probe workload so it exercises tuple-backed `metric_prefixes` and `target_fields` matching in addition to the existing run-kind matching. The registry entry keeps focused `test_command`, `coverage_command`, and `probe_command` fields, and the probe command prefers the head probe script for both base and head measurements so CI compares the same workload shape.

## Optimization

Matrix rules usually define immutable tuple literals. The previous run-kind slice cached tuple normalization for set membership, but `_rule_matches_report(...)` still rebuilt string tuples for `metric_prefixes` and `target_fields` on every call. This slice adds a small cached tuple-normalization helper for tuple inputs and keeps non-tuple iterables uncached so mutable caller data still reflects subsequent mutations.

## Validation

Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux. Use the PR-scoped performance workflow as the final merge gate before merging.
