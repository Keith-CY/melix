# Report evidence release matrix empty-role fast path

This Python-only performance slice is limited to `_release_matrix_rows(...)` in
`services/mlx-worker-python/worker/productization/report_evidence_gate.py`.

## Scope

When at least one report contributes evidence for a release-matrix role, the
release-matrix renderer still emits every configured role. Roles without
evidence historically performed two dictionary lookups and sorted an empty
fallback tuple while computing `present` and `evidence_ids`.

This slice keeps release-matrix behavior unchanged while binding each role's
evidence set once. Missing roles now reuse that single lookup to emit
`present=False` and `evidence_ids=[]`, and matching roles still sort the collected
evidence IDs exactly as before.

## Verification

The affected path remains covered by the registered PR-scoped probe
`report-evidence-gate-run-kind-set-membership`, including its focused
`test_command`, `coverage_command`, and `probe_command`. The local Linux evidence
for this slice should include:

- `services/mlx-worker-python/tests/test_report_evidence_gate.py` focused release
  matrix tests and probe-selection tests.
- Changed-scope coverage for `report_evidence_gate.py`, the focused tests, the
  PR-scoped performance tests, and `scripts/report_evidence_gate_run_kind_probe.py`.
- The registered `report-evidence-gate-run-kind-set-membership` probe before and
  after the change, with emphasis on `release_matrix_elapsed_ms_mean` and
  `release_matrix_unmatched_elapsed_ms_mean`.
