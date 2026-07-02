# Report evidence target-field rule cache

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._rule_matches_report()` target-field rules.

## Registered probe

The affected path is covered by the registered PR-scoped probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/report_evidence_gate_run_kind_probe.py`

## Optimization

Tuple-valued `target_fields` rules are immutable and reused across release evidence matrix evaluations. Cache the normalized `frozenset[str]` on the rule object, mirroring the existing run-kind and metric-prefix rule-local caches, so repeated target-field checks skip tuple normalization and cache-wrapper calls. Non-tuple iterables continue to be normalized per call so list mutation remains observable.

## Verification

1. Extend the focused target-field regression test to assert tuple rules populate and reuse the rule-local cache while list rules still reflect mutation.
2. Run the registered focused test command locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run the registered probe locally on Linux and compare against the pre-change baseline.
5. Use the PR-scoped performance workflow as the merge gate.

## Success criteria

- Focused tests pass.
- Changed-scope coverage for touched Python and probe files remains at or above 95%.
- Local and CI registered probe metrics show lower `target_field_elapsed_ms_mean` and non-regression in the aggregate `elapsed_ms_mean`.
