# Dataset source path map fast path

## Scope

This Python-only performance slice targets
`worker.productization.dataset_preparation._iter_source_file_paths` after the
scandir traversal has collected and sorted source file path strings. The behavior
remains unchanged: the helper returns a deterministically sorted `list[Path]`,
skips scandir entry errors, and does not follow directory symlinks.

## Probe coverage

The affected path is covered by the registered PR-scoped probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries and watches the dataset preparation implementation,
focused ingest tests, PR-scoped performance tests, and
`scripts/dataset_source_records_probe.py`.

## Implementation plan

1. Preserve the existing explicit `os.scandir` traversal and deterministic string
   sort.
2. Convert sorted path strings to `Path` instances through the locally bound
   `Path` constructor with `list(map(...))` to avoid the Python-level list
   comprehension loop in this final projection step.
3. Re-run the registered focused tests, changed-scope coverage command, and the
   registered probe locally on Linux before opening the PR.

## Verification boundary

This slice is Python-only and locally verifiable on Linux. The PR-scoped GitHub
Actions performance workflow remains the merge gate for the registered probe
report.

## 2026-07-19 execution note

The slice remains limited to replacing the final Python-level path projection
comprehension with `list(map(path_cls, file_paths))` after deterministic string
sorting. Behavior is unchanged: traversal still uses non-following `os.scandir`,
entry errors remain skipped, and the helper returns a sorted `list[Path]`.

Local Linux probe result for `dataset-source-records-scandir` against
`origin/main` showed a small primary traversal improvement:
`elapsed_ms_mean 12.6049 -> 12.5383 ms` and
`elapsed_ms_p95 15.9867 -> 14.2248 ms`. Secondary read/source-kind metrics also
improved in that run, while record materialization noise stayed within the
registered 5 percent warning threshold. CI PR-scoped performance remains the
merge gate.
