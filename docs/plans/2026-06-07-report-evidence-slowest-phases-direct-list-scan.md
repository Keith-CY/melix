# Report Evidence Gate Slowest Phases Direct List Scan

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._slowest_probe_phases`.

## Scope

- Preserve the top-five slowest probe phase report ordering, typed duration handling, tie behavior, and malformed-row tolerance.
- Replace the hot-loop `_dict_list(...)` materialization with direct list iteration plus an inline `dict` guard.
- Keep the slice local to report evidence gate code, its focused regression coverage, and this governing plan.

## Registered probe

The affected path is covered by the existing `report-evidence-gate-run-kind-set-membership` registered PR-scoped performance probe in `infra/perf/pr_scoped_probes.json`.

The registered probe already provides focused `test_command`, `coverage_command`, and `probe_command` entries for `services/mlx-worker-python/worker/productization/report_evidence_gate.py`, including `slowest_probe_phase_elapsed_ms_mean` in `scripts/report_evidence_gate_run_kind_probe.py`.

## Verification plan

1. Run the focused registered test command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux and confirm the touched scope remains at or above 95%.
3. Run the registered probe command locally on Linux and compare against the pre-change baseline from `origin/main`.
4. Use GitHub Actions PR-scoped performance as the merge gate before merging.

## Expected performance signal

The expected directional improvement is a reduction in `slowest_probe_phase_elapsed_ms_mean` from avoiding allocation of an intermediate filtered row list for each side of the probe summary. Overall `elapsed_ms_mean` may improve slightly; the slowest-phase metric is the primary metric for this slice.
