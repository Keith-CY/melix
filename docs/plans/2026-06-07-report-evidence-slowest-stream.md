# Report Evidence Slowest Probe Phase Duration Parsing

## Slice

Optimize one registered Python hot path in `worker.productization.report_evidence_gate`: `_slowest_probe_phases()`.

The registered `report-evidence-gate-run-kind-set-membership` probe measures `slowest_probe_phase_elapsed_ms_mean` with numeric probe durations. This slice preserves the existing top-five selection strategy while avoiding redundant `float()` conversion for duration values that are already concrete `float` objects.

## Probe Coverage

Registered probe: `report-evidence-gate-run-kind-set-membership`

The registry entry already contains focused commands for:

- tests: report evidence gate unit coverage plus PR-scoped probe selection tests
- coverage: changed-scope coverage for `report_evidence_gate.py`
- probe: `scripts/report_evidence_gate_run_kind_probe.py`

## Acceptance

- Preserve top-five ordering and tie semantics for slowest probe phases.
- Keep the slice limited to the report evidence gate hot path, its focused test, and this plan.
- Run focused local tests, changed-scope coverage, and the registered probe on Linux.
- Use the registered PR-scoped performance workflow as the CI validation source before merge.
