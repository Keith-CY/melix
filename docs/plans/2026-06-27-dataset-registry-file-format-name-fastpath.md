# Dataset registry file-format name fast path

## Scope

This Python performance slice targets the dataset registry snapshot file scan in
`services/mlx-worker-python/worker/dataset_registry/catalog.py`.

The scan already walks snapshot directories with `os.scandir`; this slice keeps
that traversal model and avoids constructing `Path` objects for regular files
whose names cannot produce a supported dataset format. The behavior remains
unchanged: README metadata and supported dataset suffixes are still emitted, and
unsupported sidecar files remain ignored.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`dataset-registry-snapshot-inference-single-pass` in
`infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`,
`coverage_command`, and `probe_command` entries for the catalog path, dataset
registry tests, PR-scoped performance tests, and
`scripts/dataset_registry_snapshot_probe.py`.

This slice extends the probe fixture with ignored `.txt` sidecar files so the
registered probe exercises the unsupported-file branch where the optimization is
measurable.

## Implementation plan

1. Add a string-name format helper shared by `_dataset_file_format()` and the
   scandir entry loop.
2. In `_iter_supported_dataset_file_entries()`, check the entry name before
   constructing `Path(entry.path)` for regular files.
3. Add a regression test proving unsupported files do not allocate `Path`
   objects while supported dataset files and README metadata still do.
4. Run focused dataset registry tests, changed-scope coverage, and the registered
   snapshot-inference probe locally on Linux. Compare `origin/main` and HEAD with
   the same updated probe fixture before accepting the slice.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Success criteria

- Focused tests pass.
- Changed-scope coverage is at least 95% for touched files.
- The registered probe reports a clear improvement or bounded allocation-path
  benefit on the sidecar-heavy fixture.
- The PR-scoped performance workflow completes successfully before merge.
