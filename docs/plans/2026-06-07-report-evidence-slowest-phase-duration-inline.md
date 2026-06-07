# Report Evidence Gate Slowest Phase Duration Inline

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._slowest_probe_phases`.

## Scope

- Preserve the top-five slowest probe phase report ordering and tie behavior.
- Inline duration normalization in the hot scan loop and local-bind the row append and dict-list helpers.
- Keep the slice local to report evidence gate code, its focused tests, and the registered PR-scoped probe configuration.

## Registered probe

The affected path is covered by the existing `report-evidence-gate-run-kind-set-membership` registered PR-scoped performance probe in `infra/perf/pr_scoped_probes.json`.

This slice updates that probe's focused `test_command` and `coverage_command` to include typed-duration coverage for the inlined normalization path. The existing `probe_command` remains the source of local and CI metrics for:

- `slowest_probe_phase_elapsed_ms_mean`
- `elapsed_ms_mean`
- related report evidence gate matrix role metrics

## Verification plan

1. Run the focused registered test command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux and confirm the touched scope remains at or above 95%.
3. Run the registered probe command locally on Linux and compare against the pre-change baseline.
4. Use GitHub Actions PR-scoped performance as the merge gate before merging.

## Expected performance signal

The expected directional improvement is a small reduction in `slowest_probe_phase_elapsed_ms_mean` from avoiding a helper-function call for each probe phase row while preserving the existing `heapq.nlargest(5, rows)` selection behavior. Overall probe mean may also improve slightly, but the slowest-phase metric is the primary metric for this slice.
