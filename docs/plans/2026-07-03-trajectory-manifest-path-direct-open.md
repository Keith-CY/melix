# Trajectory Manifest Path Direct Open Performance Slice

## Scope

This Python-only performance slice is limited to
`load_trajectory_provenance_from_snapshot_manifest()` in
`services/mlx-worker-python/worker/trajectory_provenance.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The probe
has focused `test_command`, `coverage_command`, and `probe_command` entries and
is locally runnable on Linux.

## Plan

1. Preserve the direct `open(..., "rb")` path for string manifest paths.
2. Add the same direct binary-open fast path for `Path`/`PosixPath` manifest paths so
   the hot loader avoids the extra `Path.read_bytes()` wrapper on common callers.
3. Keep generic `os.PathLike` support on the existing fallback path.
4. Update the registered probe implementation to measure the `Path` input path
   and run the focused tests, changed-scope coverage, and probe locally.

## Metrics

Local Linux validation must include the registered probe output with old/new
mean timings and a changed-scope coverage report for the touched files. GitHub
Actions PR-scoped performance remains the merge gate after the PR is opened.
