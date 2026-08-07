# Report Evidence Release Matrix Unmatched Roles

## Context

`worker.productization.report_evidence_gate._release_matrix_rows()` aggregates source evidence IDs by release-matrix role. Follow-up report-gate performance slices already made report analysis lazy for run-kind-only matrix rules, but the release-matrix row builder still stringified every source evidence ID for multi-role report rows before checking whether any role belonged to the active matrix.

## Slice

This Python-only slice keeps release evidence semantics unchanged while narrowing unmatched multi-role row overhead:

- bind `matrix.__contains__` once for the `_release_matrix_rows()` report loop;
- defer `str(...)` conversion of source evidence IDs until the first matching matrix role is found;
- preserve existing singleton-role behavior, de-duplication, row ordering, and stringified evidence IDs for matched roles.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`.

This slice extends the same registered probe with `release_matrix_unmatched_elapsed_ms_mean` so PR-scoped performance explicitly measures the newly optimized unmatched multi-role path. The registry entry keeps focused `test_command`, `coverage_command`, and `probe_command` entries.

## Verification Plan

- Run the focused report evidence gate regression tests selected by the registered probe.
- Run changed-scope coverage for `worker.productization.report_evidence_gate` through the registered `coverage_command`.
- Run `scripts/report_evidence_gate_run_kind_probe.py` locally on Linux and compare the emitted release-matrix unmatched metric before/after this slice.
- Use the PR-scoped performance workflow as the merge gate for the registered probe report.

## Success Criteria

- `_release_matrix_rows()` does not stringify evidence IDs for multi-role reports whose roles are absent from the matrix.
- Existing release matrix behavior remains unchanged for matched and singleton roles.
- Focused tests and changed-scope coverage pass locally.
- Registered probe output includes the new unmatched-role metric and remains directionally non-regressive on CI.
