# Dataset registry snapshot relative-path construction slice

## Scope

This Python-only performance slice targets the dataset registry snapshot build path in
`services/mlx-worker-python/worker/dataset_registry/catalog.py`.

The registered PR-scoped probe is
`dataset-registry-snapshot-inference-single-pass` in
`infra/perf/pr_scoped_probes.json`; it covers the dataset registry catalog path,
focused tests, changed-scope coverage, and the local/CI probe command.

## Baseline behavior

`_dataset_files(...)` iterated supported files as `Path` objects, then computed each
snapshot-relative path with `path.relative_to(snapshot_dir)` before constructing the
`DatasetFile`. For large snapshots this repeats root-relative path calculation for
every accepted file even though the recursive scanner already knows each directory
entry name and parent prefix.

## Change

Add `_iter_supported_dataset_file_entries(...)`, which carries the snapshot-relative
path string while scanning. `_dataset_files(...)` consumes `(Path, relative_path)`
entries directly and avoids per-file `Path.relative_to(...)`. The existing
`_iter_supported_dataset_files(...)` API is preserved as a thin wrapper for other
callers, keeping external behavior and ordering unchanged. The carried logical
metadata path always uses `/` separators so serialized snapshot payloads remain
platform-independent even when the host filesystem separator differs.

## Verification plan

- Run the registered probe's focused pytest command.
- Run the registered probe's changed-scope coverage command; changed scope must stay
  at or above 95%.
- Run `scripts/pr_scoped_performance_run.py` for
  `dataset-registry-snapshot-inference-single-pass` comparing `origin/main` against
  this worktree.
- Accept only if the registered probe shows a clear non-regression/improvement.
