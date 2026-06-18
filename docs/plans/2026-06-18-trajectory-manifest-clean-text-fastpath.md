# Trajectory manifest clean-text fast path

This Python-only performance slice is limited to `worker.trajectory_provenance.load_trajectory_provenance_from_snapshot_manifest` for normalized trajectory snapshot manifests loaded from JSON bytes.

## Registered probe

The affected path is already covered by the registered PR-scoped performance probe `trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `scripts/trajectory_manifest_json_load_probe.py`

## Slice

Normalized manifest JSON emitted by Melix uses exact `str` fields for the required trajectory provenance keys. The existing generic extraction path still routes those already-clean strings through the fallback stripping helper before materializing the provenance dictionary.

This slice adds an exact-dict fast path for loaded manifests when:

- `format` is exactly `agentic_tool_trace`;
- required manifest text fields are exact `str` values with no leading/trailing whitespace;
- nested copying is disabled, matching the load-from-file path.

The fallback path remains responsible for whitespace normalization, non-string values, dict subclasses, missing source aliases, and the public copy-preserving API.

## Verification

Run the registered focused test command, changed-scope coverage command, and local registered probe on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered base-vs-head report.
