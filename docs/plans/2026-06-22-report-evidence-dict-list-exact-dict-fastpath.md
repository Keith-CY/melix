# Report evidence `_dict_list` exact-dict fast path

## Scope

This Python-only performance slice is limited to
`worker.productization.report_evidence_gate._dict_list`. The helper is called
repeatedly while analyzing report evidence payload sections that are normally
already `list[dict]` values decoded from JSON.

## Optimization

Keep the existing semantics for non-list values, mixed lists, and `dict`
subclasses, but make the all-plain-`dict` path cheaper by checking exact dict
rows before falling back to the slower `isinstance(..., dict)` subclass check.
The fallback still filters malformed mixed lists exactly as before.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`,
`coverage_command`, and `probe_command` entries and reports
`dict_list_elapsed_ms_mean` in addition to the overall gate timings.

## Verification plan

1. Run the registered focused pytest command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered probe command locally on Linux.
4. Run `scripts/pr_scoped_performance_run.py` for
   `report-evidence-gate-run-kind-set-membership` against `origin/main` and
   `HEAD` and use the registered CI report as the merge gate.

## Expected performance signal

The primary expected improvement is lower `dict_list_elapsed_ms_mean` from the
exact-`dict` fast path. Overall `elapsed_ms_mean` may improve slightly, while
other sub-metrics should remain directionally stable.
