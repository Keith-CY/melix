# Report evidence lazy matrix inputs

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._report_matrix_roles`.

## Scope

- Preserve report evidence release-matrix role matching semantics.
- Avoid materializing `targets` and `metrics` lists when the active release matrix contains only run-kind-only rules.
- Keep mixed-rule behavior intact by materializing `targets` and `metrics` once on the first non-run-kind-only rule.

## Registered probe

The affected path is covered by the registered PR-scoped probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/report_evidence_gate_run_kind_probe.py`

## Verification plan

1. Run the focused report evidence tests and PR-scoped registry selection tests.
2. Run changed-scope coverage through the registered probe coverage command.
3. Run the registered probe locally on Linux and compare the pre/post metrics, especially `matrix_roles_elapsed_ms_mean` and `elapsed_ms_mean`.

GitHub Actions PR-scoped performance remains the final registered probe validation and merge gate.
