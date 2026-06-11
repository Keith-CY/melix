# Report Evidence Run-kind Value Fast Path

This Python-only performance slice is limited to the report evidence gate's
release-matrix run-kind value normalization path in
`services/mlx-worker-python/worker/productization/report_evidence_gate.py`.

Registered PR-scoped probe: `report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`. The probe already includes focused
`test_command`, `coverage_command`, and `probe_command` entries for this path.

## Slice

`_report_matrix_roles()` builds a normalized run-kind set once when the release
matrix contains run-kind-only rules. The current helper normalizes through a
`str(...)` generator for every run value, even though production benchmark and
evaluation reports normally store `run_kind` as an exact `str`.

This slice keeps the same non-string fallback behavior while adding a direct
string fast path inside `_report_run_kind_values()`.

## Validation

- Focused report evidence gate tests.
- Changed-scope coverage for the touched report evidence gate files.
- Registered PR-scoped probe locally on Linux.
- GitHub Actions remains the merge gate for the registered PR-scoped performance
  report.
