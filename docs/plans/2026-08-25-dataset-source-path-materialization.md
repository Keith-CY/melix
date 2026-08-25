# Dataset Source Path Materialization Slice

## Scope

This Python-only performance slice is limited to source file path materialization in
`services/mlx-worker-python/worker/productization/dataset_preparation.py`.
The behavioral contract remains unchanged: directory dataset ingest scans source
files with `os.scandir()`, preserves deterministic sorted order, and returns
`Path` objects for the existing downstream source-size, source-kind, read, and
record construction steps.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries covering source-file iteration, source-size accounting,
source-kind classification, source reads, inventory construction, and record
construction.

## Optimization

After the `os.scandir()` stack has collected and sorted raw filesystem path
strings, materialize the final `Path` list with an explicit list comprehension
instead of `list(map(Path, file_paths))`. The comprehension keeps the local
`Path` binding while avoiding the extra `map` iterator object on the large-file
source listing hot path.

## Validation plan

1. Run the registered focused test command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered probe locally against `origin/main` and the head branch;
   compare `elapsed_ms_mean`, `source_size_elapsed_ms_mean`, and downstream
   timing slices to ensure deterministic behavior remains unchanged and the path
   materialization slice does not regress ingest work.
4. Use GitHub Actions PR-scoped performance as the merge gate after push.

## Success criteria

- Focused tests and changed-scope coverage pass.
- The registered probe shows directionally lower `elapsed_ms_mean` without
  changing `file_count_mean`, `directory_count`, or source-kind variant counts.
- The PR-scoped performance CI report completes successfully before merge.
