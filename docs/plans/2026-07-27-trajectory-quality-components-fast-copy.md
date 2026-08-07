# Trajectory quality component fast copy

## Scope

This Python performance slice is limited to the common
`trajectory_quality_metrics.components` payload copied by
`services/mlx-worker-python/worker/trajectory_provenance.py` while loading
trajectory snapshot manifests.

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The probe
has focused `test_command`, `coverage_command`, and `probe_command` entries for
trajectory provenance behavior, changed-scope coverage, and the manifest JSON
load workload that repeatedly copies quality metric components.

## Plan

Most quality metric component payloads are exact JSON dictionaries with
`name`, `score`, `passed`, and a scalar `labels` list. Copy that component list
in one dedicated pass before falling back to the generic recursive provenance
copy helper. The defensive copy boundary remains intact: the components list,
component dictionaries, and labels lists are still copied so caller mutations do
not leak into normalized provenance.

## Verification

Run the registered focused tests, changed-scope coverage, and
`trajectory-manifest-json-load` probe locally on Linux before pushing. GitHub
Actions PR-scoped performance remains the merge gate for the registered probe
report.
