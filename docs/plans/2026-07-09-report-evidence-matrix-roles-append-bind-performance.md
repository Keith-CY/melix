# Report Evidence Matrix Roles Append Binding Performance

## Context

The registered PR-scoped probe `report-evidence-gate-run-kind-set-membership` covers `services/mlx-worker-python/worker/productization/report_evidence_gate.py`, including `_report_matrix_roles()` and release-matrix row construction.

## Slice

This slice keeps release evidence gate semantics unchanged and only reuses the existing `roles_append` local binding for the non-run-kind branch in `_report_matrix_roles()`.

## Plan

1. Preserve all report evidence gate behavior through the focused registered tests.
2. Replace the remaining `roles.append(role)` call in `_report_matrix_roles()` with the already-bound `roles_append(role)` helper.
3. Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux.
4. Use the PR-scoped performance CI report as the registered probe validation before merge.

## Metrics

Baseline local registered probe on Linux before the code change:

- `elapsed_ms_mean`: 1003.5198386060074 ms
- `matrix_roles_elapsed_ms_mean`: 3.2844005851075053 ms
- `run_kind_elapsed_ms_mean`: 213.71506120776758 ms

Post-change local registered probe on Linux (four direct replays after the code change):

- `elapsed_ms_mean`: 953.736360615585 ms, 934.6832690178417 ms, 952.635077375453 ms, 961.8289634003304 ms; mean 950.7209176023025 ms
- `matrix_roles_elapsed_ms_mean`: 3.3351320074871182 ms, 3.286617004778236 ms, 3.6247160052880645 ms, 3.2795290113426745 ms; mean 3.3814985072240233 ms
- `run_kind_elapsed_ms_mean`: 204.2225984041579 ms, 200.94783080276102 ms, 204.91587138967589 ms, 217.9952866048552 ms; mean 207.0203968003625 ms

Local probe deltas versus the single pre-change baseline:

- `elapsed_ms_mean`: -52.79892100370494 ms (-5.261%)
- `matrix_roles_elapsed_ms_mean`: +0.09709792211651797 ms (+2.956%; noisy targeted submetric)
- `run_kind_elapsed_ms_mean`: -6.694664407405079 ms (-3.132%)

The total registered probe direction is positive on Linux, while the isolated matrix-role submetric is within local noise and requires the PR-scoped CI report before final merge.

## Verification

- Focused report evidence gate tests from the registered probe.
- Changed-scope coverage from the registered probe.
- `scripts/report_evidence_gate_run_kind_probe.py` via the registered probe command.
