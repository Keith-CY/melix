# Trajectory manifest path type binding

## Scope

This Python-only performance slice is limited to
`worker.trajectory_provenance.load_trajectory_provenance_from_snapshot_manifest`
path-dispatch before the manifest JSON read.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The probe
already has focused `test_command`, `coverage_command`, and `probe_command`
entries and watches:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/trajectory_manifest_json_load_probe.py`

## Slice

The manifest loader already has direct branches for exact `str`, exact concrete
`pathlib.Path`, and generic `os.PathLike` inputs. This slice binds
`_TYPE(manifest_path)` once and reuses it for the exact `str` and exact `Path`
branches instead of resolving `type(manifest_path)` twice in the hot path.
Generic path-like compatibility remains unchanged through `os.fspath()`.

## Verification

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux before opening the PR. GitHub Actions
PR-scoped performance remains the merge gate for the registered base-vs-head
report.
