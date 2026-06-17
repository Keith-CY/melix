# Report Evidence Gate Release Matrix Membership Fast Path

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._release_matrix_rows`.

## Scope

- Preserve release evidence matrix row ordering, required/present flags, evidence id stringification, and sorted evidence id output.
- Avoid rebuilding a temporary `set(matrix)` on each release-matrix pass and avoid `setdefault(..., set())` empty-set allocation for roles that already have evidence.
- Keep the slice local to report evidence gate code, its focused registered tests, and this governing plan.

## Registered probe

The affected path is covered by the existing `report-evidence-gate-run-kind-set-membership` registered PR-scoped performance probe in `infra/perf/pr_scoped_probes.json`.

The registered probe provides focused `test_command`, `coverage_command`, and `probe_command` entries for `services/mlx-worker-python/worker/productization/report_evidence_gate.py`, and it reports `release_matrix_elapsed_ms_mean` from `scripts/report_evidence_gate_run_kind_probe.py`.

## Verification plan

1. Run the focused registered test command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux and confirm the touched scope remains at or above 95%.
3. Run the registered probe command locally on Linux and compare `release_matrix_elapsed_ms_mean` against the pre-change `origin/main` baseline.
4. Use GitHub Actions PR-scoped performance as the merge gate before merging.

## Expected performance signal

The primary expected signal is lower `release_matrix_elapsed_ms_mean` from avoiding a temporary matrix-role set allocation and repeated empty-set allocations in the evidence aggregation path. Overall `elapsed_ms_mean` may improve slightly; non-release-matrix submetrics are not targeted by this slice.
