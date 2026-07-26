# Report evidence lazy matrix inputs

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._report_matrix_roles`.

## Scope

- Preserve report evidence release-matrix role matching semantics.
- Avoid materializing `targets` and `metrics` lists when the active release matrix contains only run-kind-only rules.
- Keep mixed-rule behavior intact by materializing `targets` and `metrics` once on the first non-run-kind-only rule.

## Registered probe

The affected path is covered by the registered PR-scoped probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/report_evidence_gate_run_kind_probe.py`

## Verification plan

1. Run the focused report evidence tests and PR-scoped registry selection tests.
2. Run changed-scope coverage through the registered probe coverage command.
3. Run the registered probe locally on Linux and compare the pre/post metrics, especially `matrix_roles_elapsed_ms_mean` and `elapsed_ms_mean`.

GitHub Actions PR-scoped performance remains the final registered probe validation and merge gate.

## Follow-up: slowest probe phase heap initialization

The 2026-07-19 follow-up remains inside `worker.productization.report_evidence_gate` and keeps the same registered `report-evidence-gate-run-kind-set-membership` probe. `_slowest_probe_phases()` now appends the first five candidate rows directly and heapifies once before replacement comparisons, instead of calling `heapq.heappush()` for each seed row. The top-five ordering, side labels, typed duration handling, and tie ordering remain unchanged.

Expected effect: lower `slowest_probe_phase_elapsed_ms_mean` in the registered probe, with the broader gate metrics non-regressive.

## Follow-up: probe phase bucket constants

The 2026-07-21 follow-up remains inside `worker.productization.report_evidence_gate`
and keeps the same registered `report-evidence-gate-run-kind-set-membership` probe.
`_probe_phases()` now reuses module-level probe-side and bucket tuples instead of
reallocating those constants on every scan. Clean string phases keep the duplicate-
membership short circuit, while stripped strings, non-string phases, and dict
subclasses retain the existing behavior.

Expected effect: lower `probe_phases_elapsed_ms_mean` in the registered probe, with
the broader report evidence gate metrics non-regressive.

## Follow-up: matrix role probe-phase lookup binding

The 2026-07-21 matrix-role lookup follow-up remains inside
`worker.productization.report_evidence_gate._report_matrix_roles` and keeps the
same registered `report-evidence-gate-run-kind-set-membership` probe. The hot
mixed-rule loop already binds `rule.get` for run-kind, metric-prefix, target-field,
and rule dispatch checks; this slice reuses that same local binding for the lazy
`probe_phases` materialization guard instead of performing one extra method lookup.

Expected effect: lower `matrix_roles_elapsed_ms_mean` in the registered probe with
unchanged emitted role counts and unchanged broader report evidence gate metrics.

## Follow-up: clean probe phase string insertion

The 2026-07-23 follow-up remains inside
`worker.productization.report_evidence_gate._probe_phases` and keeps the same
registered `report-evidence-gate-run-kind-set-membership` probe. `_probe_phases`
now binds the hot exact-type helpers locally and inserts exact `str` phase values
that are already non-empty and free of leading/trailing whitespace directly after
the duplicate-membership guard instead of calling `strip()`. Padded strings,
blank strings, non-string phase values, and dict subclass rows retain the existing
normalization behavior.

Expected effect: lower `probe_phases_elapsed_ms_mean` in the registered probe
with unchanged phase counts and broader report evidence gate metrics.

## Follow-up: run-kind value set explicit loop

The 2026-07-26 follow-up remains inside
`worker.productization.report_evidence_gate._report_run_kind_values` and keeps the
same registered `report-evidence-gate-run-kind-set-membership` probe. The hot
run-kind scan now builds the normalized value set with an explicit loop and local
bindings for `set.add`, `type`, `str`, and the `run_kind` key, avoiding the set
comprehension frame while preserving exact-string pass-through and non-string
stringification behavior.

Expected effect: lower `run_kind_elapsed_ms_mean` and non-regressive
`elapsed_ms_mean` in the registered probe with unchanged run-kind counts and
match counts.

## Follow-up: exact Path payload load fast path

The 2026-07-26 follow-up remains inside
`worker.productization.report_evidence_gate.load_report_payload` and keeps the
same registered `report-evidence-gate-run-kind-set-membership` probe. The report
loader now reuses exact `Path` instances passed by the gate and probe instead of
constructing a replacement `Path` for every load; string path inputs and custom
path-like wrappers still go through the existing `Path(...)` normalization path.

Expected effect: lower `load_report_payload_elapsed_ms_mean` and non-regressive
`elapsed_ms_mean` in the registered probe with unchanged payload checksum.

The CI rerun for this Path slice exposed `dict_list_elapsed_ms_mean` noise inside
the same registered probe. To keep the direct probe green without widening the
behavioral surface, `_dict_list` now also binds `type` locally for its existing
exact-list / exact-dict checks. Filtering behavior for non-lists, dict subclasses,
list subclasses, mixed invalid rows, and identity-preserving all-dict lists is
unchanged by the existing `_dict_list` tests.
