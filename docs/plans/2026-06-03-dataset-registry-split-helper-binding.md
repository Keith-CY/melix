# Dataset registry split helper binding

## Scope

This Python-only performance slice is limited to the split matching helper in
`services/mlx-worker-python/worker/dataset_registry/catalog.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`dataset-registry-limited-read-streaming` in `infra/perf/pr_scoped_probes.json`.
The registry entry has focused `test_command`, `coverage_command`, and
`probe_command` entries and is locally verifiable on Linux.

## Optimization

`_path_matches_split()` invokes `_path_part_matches_split()` once for the file
name and then for each parent path part. Bind the helper once per call and reuse
the local binding through the filename and parent-part checks. This keeps split
matching behavior unchanged while avoiding repeated global helper lookups in the
registered split-match probe path.

## Verification Plan

- Run the registered focused tests for `dataset-registry-limited-read-streaming`.
- Run the registered changed-scope coverage command and require at least 95%
  coverage for the touched scope.
- Run the registered local probe on Linux before and after the change and compare
  `elapsed_ms_mean`, `path_constructor_calls_mean`, and `peak_bytes_mean`.
- Use PR-scoped performance CI as the merge gate before squash merging.

## Success Criteria

- Existing split matching semantics remain unchanged.
- Changed-scope coverage remains at or above the repository threshold.
- The registered probe shows a directionally lower or stable `elapsed_ms_mean`
  with unchanged `path_constructor_calls_mean`.
