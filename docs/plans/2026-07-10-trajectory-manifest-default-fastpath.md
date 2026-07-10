# Trajectory manifest defaulted-field fast path

This Python-only performance slice is limited to
`worker.trajectory_provenance.load_trajectory_provenance_from_snapshot_manifest`
for normalized agentic trajectory snapshot manifests loaded from JSON bytes.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The probe
entry already defines focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `scripts/trajectory_manifest_json_load_probe.py`

## Slice

Trajectory snapshot manifests may omit `trajectory_schema_version` and
`trajectory_split`, which the generic extractor defaults to
`melix.agentic_tool_trace.v1` and `train`. Before this slice, the exact-dict load
fast path rejected those otherwise clean manifests and routed them through the
fallback text-stripping path.

This slice keeps those defaults unchanged while allowing the fast path to handle
missing schema and split values directly. Explicit malformed or whitespace-padded
values still fall back to the generic normalizer so compatibility behavior is
preserved.

The local probe workload now omits the defaulted fields to measure this specific
path. GitHub Actions PR-scoped performance remains the merge gate for the
registered base-vs-head report.

## Verification

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux before opening the PR.
