# Report Evidence Slowest Phase Bounded Heap

## Scope

This Python-only performance slice is limited to the report evidence gate slowest
probe phase extraction in `services/mlx-worker-python/worker/productization/report_evidence_gate.py`.
The behavior remains unchanged: the gate still reports at most five slowest
probe phase rows across baseline and candidate summaries, preserving duration
ordering and existing tie order semantics.

## Registered Probe

The affected path is already covered by the registered PR-scoped performance
probe `report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for the report
evidence gate tests, changed-scope coverage, and command-json probe metrics.

## Optimization Plan

1. Keep the existing row validation and typed duration coercion semantics.
2. Replace the generator plus `heapq.nlargest(5, ...)` slowest-phase selection
   with an explicit bounded min-heap of size five.
3. Sort only the five retained rows before returning the public result payload.
4. Run the registered focused test command, changed-scope coverage command, and
   registered command-json probe locally on Linux.
5. Use GitHub Actions PR-scoped performance as the merge gate after push.

## Validation Notes

The local Linux validation source is the registered Python probe. The expected
metric direction is a lower `slowest_probe_phase_elapsed_ms_mean` and a neutral
or improved aggregate `elapsed_ms_mean` without changing report-evidence gate
semantics.
