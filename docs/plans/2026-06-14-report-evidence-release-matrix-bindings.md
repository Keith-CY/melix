# Report Evidence Release Matrix Local Bindings

## Slice

Optimize one Python hot path in `worker.productization.report_evidence_gate`:
`_release_matrix_rows(...)` aggregates evidence IDs by release-matrix role for
PR evidence reports. The current loop repeatedly performs global method lookup
for matrix membership and evidence-map lookup while processing many synthetic
reports in the registered probe.

This slice binds those lookups locally inside `_release_matrix_rows(...)` and
avoids allocating an unused empty `set()` for matrix roles that have no evidence.
It does not change release matrix semantics, report validation, probe registry
shape, or output schemas.

## Registered Probe

The affected path is already covered by the registered PR-scoped performance
probe `report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`,
`coverage_command`, and `probe_command` entries covering:

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/report_evidence_gate_run_kind_probe.py`

## Verification Plan

1. Run the registered probe on `origin/main` before the edit and record the
   release-matrix baseline.
2. Apply the local-binding optimization in `_release_matrix_rows(...)` only.
3. Run focused pytest from the registered probe.
4. Run changed-scope coverage from the registered probe.
5. Run the registered probe locally on Linux and require an improvement or a
   clear no-merge decision.
6. Use PR-scoped performance CI as the merge gate.

## Metrics

Primary metric: `release_matrix_elapsed_ms_mean` from
`report-evidence-gate-run-kind-set-membership`.

Secondary guard metrics: `elapsed_ms_mean`, `matrix_roles_elapsed_ms_mean`, and
existing informational role/report counts must remain valid.
