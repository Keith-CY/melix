# Report Evidence Matrix Evidence Normalization Deferral

## Goal

Reduce release-matrix row construction overhead in `worker.productization.report_evidence_gate` when reports list release-matrix roles that are not present in the active release evidence matrix.

## Linux verification scope

This is a Python productization slice and is locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped probe.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`. The entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/report_evidence_gate_run_kind_probe.py`

The registered probe reports `release_matrix_unmatched_elapsed_ms_mean`, which directly measures the unmatched-role case targeted by this slice.

## Slice

Defer `source_evidence_ids` string normalization in `_release_matrix_rows(...)` until after a report has at least one role present in the active matrix. Reports with only unmatched roles still produce the same absent release-matrix rows, but avoid constructing a temporary normalized evidence-id set that cannot be emitted.

## Verification plan

1. Add a regression test proving unmatched roles do not normalize evidence IDs.
2. Run focused report-evidence tests and registered probe smoke tests.
3. Run changed-scope coverage for the registered probe paths.
4. Run the registered local Linux probe against `origin/main` and the branch, comparing `release_matrix_unmatched_elapsed_ms_mean`.
5. Use hosted PR-scoped performance CI as the merge gate.

## Success metrics

- Focused pytest passes.
- Changed-scope coverage is at least 95% for touched executable Python scope.
- Local registered probe shows lower `release_matrix_unmatched_elapsed_ms_mean` without changing emitted-row counts.
- `git diff --check` passes.
