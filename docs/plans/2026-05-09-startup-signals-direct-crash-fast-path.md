# Startup Signals Direct Crash Fast Path

## Scope

This Python-only performance slice keeps startup failure classification behavior equivalent while avoiding startup log reads when the direct `error_text` already identifies a control-plane crash.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `startup-signals-lazy-worker-log-excerpts` in `infra/perf/pr_scoped_probes.json`.

This slice extends the probe with direct-control-plane-crash metrics:

- `direct_control_crash_elapsed_ms_mean`
- `direct_control_crash_log_reads_mean`

The existing focused `test_command`, `coverage_command`, and `probe_command` remain attached to the probe.

## Expected Behavior

- Direct host-port-conflict error text still short-circuits all log reads.
- Direct crash-pattern error text now classifies as `control_plane_crash` without reading stale control-plane or worker logs.
- Log-backed control-plane and worker crash classification remain unchanged when direct error text is generic.

## Verification Plan

Run the registered focused startup-signals tests, changed-scope coverage, and the registered probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate.
