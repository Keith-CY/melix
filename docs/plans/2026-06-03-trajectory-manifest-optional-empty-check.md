# Trajectory Manifest Optional Empty Check Fast Path

## Scope

Optimize one Python hot path in `services/mlx-worker-python/worker/trajectory_provenance.py`:
optional manifest field extraction should skip missing and empty-string fields
without constructing a tuple membership candidate on every optional field.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for `trajectory_provenance.py`,
`test_trajectory_provenance.py`, `test_pr_scoped_performance.py`, and
`scripts/trajectory_manifest_json_load_probe.py`.

## Implementation Plan

1. Preserve the existing semantics: skip `None` and empty-string optional fields,
   retain all other values including `0`, `False`, containers, and non-empty
   strings.
2. Replace tuple membership with explicit `is None` / `== ""` checks in the
   manifest optional-field loop only.
3. Run focused tests, changed-scope coverage, and the registered manifest JSON
   load probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the CI validation source.

## Verification Notes

Linux local validation is expected for this Python slice. Swift/macOS runtime
validation is not applicable.
