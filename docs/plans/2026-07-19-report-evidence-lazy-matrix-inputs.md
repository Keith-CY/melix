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

## Follow-up: slowest probe phase heap initialization

The 2026-07-19 follow-up remains inside `worker.productization.report_evidence_gate` and keeps the same registered `report-evidence-gate-run-kind-set-membership` probe. `_slowest_probe_phases()` now appends the first five candidate rows directly and heapifies once before replacement comparisons, instead of calling `heapq.heappush()` for each seed row. The top-five ordering, side labels, typed duration handling, and tie ordering remain unchanged.

Expected effect: lower `slowest_probe_phase_elapsed_ms_mean` in the registered probe, with the broader gate metrics non-regressive.
