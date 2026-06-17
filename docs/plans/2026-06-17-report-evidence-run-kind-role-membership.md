# Report evidence run-kind role membership slice

## Scope

This Python-only performance slice is limited to
`worker.productization.report_evidence_gate._report_matrix_roles` for release
matrix rules that only match `run_kinds`. These rules are common in release
evidence matrices, and the report's run-kind values are already normalized once
per report.

Affected files:

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `docs/plans/2026-06-17-report-evidence-run-kind-role-membership.md`

## Registered probe

The affected path is covered by the registered PR-scoped probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`. The registry entry already defines focused
`test_command`, `coverage_command`, and `probe_command` entries. The primary
metric for this slice is `matrix_roles_elapsed_ms_mean`, with
`elapsed_ms_mean` as the aggregate registered-probe signal.

## Intended change

For run-kind-only tuple rules, avoid constructing or looking up a normalized
frozenset per matrix role. Instead, compare the tuple entries directly against
the once-per-report run-kind value set, preserving stringification behavior for
non-string rule entries. Non-tuple run-kind iterables continue to use the
existing normalization helper so mutable rule containers still reflect mutation.

## Validation

Run the registered focused tests, changed-scope coverage, and registered probe
locally on Linux before opening the PR. CI remains the merge gate for the
registered PR-scoped performance workflow.
