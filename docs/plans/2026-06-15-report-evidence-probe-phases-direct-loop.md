# Report Evidence Probe Phases Direct Loop Performance Slice

Date: 2026-06-15

## Scope

This slice optimizes the Python release-evidence gate probe phase scan in
`services/mlx-worker-python/worker/productization/report_evidence_gate.py`.
The change is limited to `_probe_phases`, which extracts phase names from the
registered `probe_summary` buckets for baseline and candidate reports.

## Plan or Spec

The existing implementation delegates each phase bucket through `_dict_list`.
That helper creates a filtered temporary list of dict rows before `_probe_phases`
iterates it. For the release matrix runtime-check path, `_probe_phases` only
needs a single read-only pass over each bucket.

The optimized path keeps the same semantics while avoiding the per-bucket list
allocation:

- scan only `baseline` and `candidate` summaries;
- scan only `slowest_phases`, `failed_phases`, `skipped_phases`, and
  `fallback_phases`;
- ignore non-list buckets;
- ignore non-dict rows;
- preserve `str(row.get("phase", "")).strip()` phase normalization;
- add only non-empty normalized phases.

## Registered Probe

Affected paths are covered by the registered PR-scoped performance probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`.

The probe entry includes:

- focused `test_command` for report evidence gate behavior and probe registry
  selection tests;
- focused `coverage_command` with changed-scope coverage reporting;
- `probe_command` via `scripts/report_evidence_gate_run_kind_probe.py`, including
  `matrix_roles_elapsed_ms_mean`, `release_matrix_elapsed_ms_mean`, and related
  evidence gate metrics.

## Verification Plan

1. Run the focused regression test added for `_probe_phases` bucket filtering.
2. Run the registered probe focused `test_command`.
3. Run the registered changed-scope `coverage_command`; touched scope must remain
   at or above 95% measured coverage.
4. Run the registered `probe_command` locally on Linux and compare with the
   baseline collected before the implementation.
5. Let GitHub Actions run the PR-scoped performance workflow and use that report
   as the merge gate.

## Success Metrics

- Behavior tests pass with unchanged bucket filtering semantics.
- Changed-scope coverage is at least 95%.
- Registered probe metrics show no regression, with expected improvement in
  `matrix_roles_elapsed_ms_mean` and/or total `elapsed_ms_mean` from removing
  `_dict_list` temporary list allocation in the probe phase scan.

## Known Gaps

This is a Python-only slice and is locally validated on Linux. It does not claim
Swift runtime performance impact.
