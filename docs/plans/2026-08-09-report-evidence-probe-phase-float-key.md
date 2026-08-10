# Report Evidence Probe Phase Float-Key Fast Path

## Slice

Optimize exactly one Python hot path in `worker.productization.report_evidence_gate._probe_phase_duration_key(...)`, used by `_slowest_probe_phases(...)` when ranking PR/report probe phase rows.

The affected path is covered by the registered PR-scoped performance probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for `report_evidence_gate.py`, its focused tests, and `scripts/report_evidence_gate_run_kind_probe.py`.

## Hypothesis

Probe summaries commonly carry `duration_ms` as an exact JSON-decoded `float`. The previous helper always dispatched through `float(duration or 0.0)` after the generic type check, even for exact floats. Returning exact floats directly preserves bool rejection, integer/string/subclass coercion, and invalid-value fallback while avoiding an extra conversion in the slowest-phase ranking loop.

## Scope

- Preserve top-five slowest phase ordering and tie behavior.
- Preserve bool durations ranking as unusable `0.0`.
- Preserve integer, string, float-subclass, empty-string, missing, and invalid duration behavior.
- Do not change report loading, matrix-role matching, rendering, probe registry, or generated artifacts.

## Verification

Run the registered focused tests, changed-scope coverage command, and command-json probe locally on Linux. CI PR-scoped performance must complete successfully before merge.
