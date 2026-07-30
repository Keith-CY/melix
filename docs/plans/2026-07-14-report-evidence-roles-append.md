# Report evidence matrix-role append binding

## Slice

This slice keeps report evidence role detection behavior unchanged while reusing the already-bound `roles_append` local in the generic `_report_matrix_roles` match branch.

## Registered probe

The affected path is covered by the registered PR-scoped probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- `test_command` for report evidence gate behavior and probe registry coverage.
- `coverage_command` for changed-scope coverage on `report_evidence_gate.py`, tests, and the probe script.
- `probe_command` via `scripts/report_evidence_gate_run_kind_probe.py`, which measures run-kind, metric-prefix, target-field, release-matrix, matrix-role, probe-phase, and dict-list hot paths.

## Implementation

`_report_matrix_roles` already binds `roles.append` to `roles_append` before scanning matrix rules. The run-kind-only branch used that local, but the generic rule branch still performed an attribute lookup. This slice changes only that append site.

## Success criteria

- Existing report evidence gate tests pass.
- Changed-scope coverage remains at or above the repository threshold.
- The registered probe reports comparable or lower matrix-role elapsed time without semantic drift.
