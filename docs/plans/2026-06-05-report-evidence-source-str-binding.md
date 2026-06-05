# Report Evidence Source ID String Binding Performance Slice

## Scope

This Python-only slice is limited to `_release_matrix_rows(...)` in
`services/mlx-worker-python/worker/productization/report_evidence_gate.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`. The probe entry already includes focused
`test_command`, `coverage_command`, and `probe_command` values and runs
`scripts/report_evidence_gate_run_kind_probe.py`, which emits
`release_matrix_elapsed_ms_mean` along with the aggregate gate timings.

## Optimization hypothesis

Release-matrix row construction stringifies every source evidence id while
accumulating evidence sets. Binding `str` once in `_release_matrix_rows(...)`
removes repeated global lookups in the single-role and multi-role accumulation
paths while preserving the existing set de-duplication and sorted output.

## Verification plan

Run the registered focused test command, registered changed-scope coverage
command, the registered probe locally on Linux, and a local `origin/main` versus
head probe comparison before pushing. CI remains the merge gate for the
registered PR-scoped performance report.
