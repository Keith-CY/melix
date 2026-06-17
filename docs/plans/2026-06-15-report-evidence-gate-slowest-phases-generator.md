# Report Evidence Gate Slowest Phase Top-K Streaming

This Python performance slice is limited to `worker.productization.report_evidence_gate._slowest_probe_phases`.

## Scope

- Preserve the existing release evidence gate output shape and deterministic top-five ordering.
- Replace materializing every candidate slowest phase before `heapq.nlargest` with a generator-backed top-k selection so the probe only streams rows into the heap selection.
- Do not change release-matrix role matching, telemetry validation, or report rendering behavior.

## Registered Probe

The affected path is already covered by the registered PR-scoped probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`. That entry includes focused `test_command`, `coverage_command`, and `probe_command` values and reports the `slowest_probe_phase_elapsed_ms_mean` metric for this slice.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux before opening the PR. The PR-scoped performance workflow remains the merge gate for the registered probe report.
