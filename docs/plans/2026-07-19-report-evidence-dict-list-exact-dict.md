# Report evidence gate exact-dict list fast path

## Scope

This Python-only performance slice is limited to
`worker.productization.report_evidence_gate._dict_list(...)`, which normalizes
report-evidence payload sections to `list[dict[str, object]]` while preserving
identity for already-valid dictionary lists.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/report_evidence_gate_run_kind_probe.py`

The existing probe reports `dict_list_elapsed_ms_mean`,
`dict_list_rows_per_call`, and `dict_list_identity_hits`; those metrics are the
primary evidence for this exact-dict fast path.

## Implementation plan

1. Preserve `_dict_list(...)` semantics for exact `list`, list subclasses,
   exact `dict` rows, dict subclasses, mixed rows, and non-list inputs.
2. Bind the `dict` type and `isinstance` helper once per `_dict_list(...)` call so
   exact-dict list scans and fallback filtering avoid repeated global lookups.
3. Run the focused report-evidence tests, changed-scope coverage command,
   `git diff --check`, and the registered local Linux probe before opening the
   PR.
4. Use GitHub Actions PR-scoped performance as the merge gate for the registered
   probe result.

## Success criteria

- Focused behavior tests pass.
- Changed-scope coverage for the touched report-evidence scope remains at or
  above the repository threshold.
- Local registered probe shows lower `dict_list_elapsed_ms_mean` versus the
  pre-change baseline without changing `dict_list_identity_hits` or checksum.
- PR-scoped performance CI selects and completes the registered probe for this
  path before merge.
