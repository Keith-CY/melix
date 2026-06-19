# Dataset Source Path Materialization Performance

This Python-only performance slice is limited to dataset source file path
materialization in `worker.productization.dataset_preparation._iter_source_file_paths`.

Registered PR-scoped probe: `dataset-source-records-scandir` in
`infra/perf/pr_scoped_probes.json`. The affected path already has focused
`test_command`, `coverage_command`, and `probe_command` entries.

## Optimization

Keep the existing `os.scandir` stack and deterministic string sort, then
materialize the final `Path` objects with `list(map(Path, file_paths))` instead
of a Python list comprehension. This preserves the public helper contract and
ordering while moving the per-element constructor loop through the C-level map
iterator on large source trees.

## Verification Plan

Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux. Accept this slice only if behavior tests pass,
changed-scope coverage remains at or above the repository threshold, and the
registered probe shows a stable elapsed-time improvement without changing file
counts or source-kind classification.
