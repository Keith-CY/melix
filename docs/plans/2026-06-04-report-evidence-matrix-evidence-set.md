# Report evidence matrix evidence-id set accumulation

## Slice

Optimize the report evidence gate release-matrix row builder by accumulating
source evidence IDs in per-role sets during one report pass, instead of nesting
one report scan per configured matrix role.

## Scope

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `scripts/report_evidence_gate_run_kind_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Behavior Contract

The release matrix output remains unchanged:

- one output row per configured role
- `present` reflects whether any matching source evidence exists
- `evidence_ids` stays sorted and deduplicated
- non-list `source_evidence_ids` values are ignored, matching the existing
  analyzed-report shape

## Performance Probe

The existing registered PR-scoped probe
`report-evidence-gate-run-kind-set-membership` covers the report evidence gate
path. This slice extends that probe with a release-matrix-row timing metric while
keeping the legacy aggregate `elapsed_ms_mean` comparable with the pre-slice
run-kind/metric-prefix/target-field baseline:

- `release_matrix_elapsed_ms_mean` (`lower_is_better`)
- `release_matrix_role_count` (informational)
- `release_matrix_report_count` (informational)

## Local Verification Plan

1. Run the registered focused test command.
2. Run the registered changed-scope coverage command.
3. Run the registered probe command on Linux and compare with `origin/main`.

## Linux Boundary

This is a Python worker/productization slice and is locally verifiable on Linux.
