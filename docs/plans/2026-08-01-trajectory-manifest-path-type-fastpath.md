# Trajectory manifest exact-Path conversion fast path

## Scope

This Python-only performance slice is limited to
`worker.trajectory_provenance.load_trajectory_provenance_from_snapshot_manifest`
when callers pass the common concrete `pathlib.Path` type.

## Registered probe

The affected path remains covered by the registered PR-scoped performance probe
`trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The probe
already defines focused `test_command`, `coverage_command`, and `probe_command`
entries for:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `scripts/trajectory_manifest_json_load_probe.py`

## Slice

The manifest loader already avoids `Path.read_text()` and uses direct binary
open for manifest JSON. This slice narrows one remaining hot-path conversion:
exact concrete `Path` values now use the locally-bound `str` conversion directly
instead of routing through `os.fspath()` on every manifest load. Generic
`os.PathLike` callers still use `os.fspath()` so custom path-like compatibility
is preserved.

## Verification

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux before opening the PR. GitHub Actions
PR-scoped performance remains the merge gate for the registered base-vs-head
report.
