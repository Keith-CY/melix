# Report Evidence Empty Release Matrix Fast Path

## Goal

Reduce release-matrix row construction overhead in `worker.productization.report_evidence_gate` when analyzed reports do not contribute evidence for any configured release-matrix role.

## Linux verification scope

This is a Python productization slice and is locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped probe.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`. The entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/report_evidence_gate_run_kind_probe.py`

The probe includes `release_matrix_unmatched_elapsed_ms_mean`, `release_matrix_unmatched_empty_rows`, and related release-matrix metrics, which directly cover this slice.

## Slice

Add an empty-evidence fast path to `_release_matrix_rows(...)`: after scanning reports, if no evidence IDs were associated with any configured matrix role, return absent rows directly. This avoids per-role dictionary lookups, empty tuple defaults, and `sorted(...)` calls while preserving row order, required/default handling, descriptions, and `present=False`/`evidence_ids=[]` semantics.

## Verification plan

1. Add a regression test for the empty-evidence matrix path.
2. Run focused report-evidence tests and the registered probe smoke test.
3. Run changed-scope coverage for the registered probe paths.
4. Run the registered local Linux probe before and after the change and compare `release_matrix_unmatched_elapsed_ms_mean`.
5. Use hosted PR-scoped performance CI as the merge gate.

## Success metrics

- Focused pytest passes.
- Changed-scope coverage is at least 95% for touched executable Python scope.
- Local registered probe shows lower `release_matrix_unmatched_elapsed_ms_mean` without changing emitted-row counts.
- `git diff --check` passes.
