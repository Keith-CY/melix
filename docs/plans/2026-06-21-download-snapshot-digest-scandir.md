# Download Snapshot Digest Scandir Performance Slice

## Scope

Optimize the strict managed-download directory snapshot digest path in
`services/mlx-worker-python/worker/model_ops/download_pipeline.py`.

The current digest builder uses `Path.rglob("*")`, then calls `is_file`,
`is_symlink`, and `stat` through `Path` objects before opening each file. This
slice keeps the digest format and sorted traversal semantics unchanged while
using a single explicit `os.scandir` stack that avoids following symlinked files
or directories.

## Registered Probe

Affected paths are covered by the registered PR-scoped performance probe
`download-pipeline-directory-size-single-stat` in
`infra/perf/pr_scoped_probes.json`. This slice extends that existing probe to
exercise the strict snapshot digest path in addition to the existing download
snapshot manifest path. The probe entry has focused `test_command`,
`coverage_command`, and `probe_command` entries.

## Verification Plan

- Add regression tests proving `_sha256_directory_snapshot` no longer depends on
  `Path.rglob` and still ignores symlinked entries.
- Run the registered focused test command locally on Linux.
- Run the registered changed-scope coverage command locally on Linux.
- Run the registered probe command locally on Linux and compare the digest path
  against the prior `Path.rglob` baseline in the probe payload.
- Use PR-scoped performance CI as the merge gate for the registered probe report.

## Expected Metrics

The probe reports:

- `digest_elapsed_ms_mean` / `digest_elapsed_ms_min`: optimized scandir snapshot
  digest timing.
- `baseline_digest_elapsed_ms_mean`: in-probe `Path.rglob` baseline timing.
- `digest_delta_ms`: optimized mean minus baseline mean; lower than zero is the
  target for this slice.

## Known Boundaries

This is a Python-only Linux-verifiable slice. No Swift runtime effect is claimed.
