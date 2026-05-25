# Dataset Source Records scandir Slice

## Scope

This Python performance slice is limited to dataset ingest source-file discovery in
`services/mlx-worker-python/worker/productization/dataset_preparation.py`. It does
not change dataset record parsing, cleaning controls, segmentation behavior,
protobuf schemas, or dependencies.

## Optimization Hypothesis

Dataset ingest currently materializes source files with `Path.rglob("*")` and then
filters files. For large raw-input trees this walks through `Path` glob machinery
and allocates `Path` objects for non-file entries before ingest can classify each
source. Replacing that discovery step with an explicit `os.scandir(...)` stack,
while returning the same sorted `Path` list, should reduce source discovery
latency without changing deterministic source ordering or operator-failure
behavior.

## Registered Probe

This slice registers `dataset-source-records-scandir` in
`infra/perf/pr_scoped_probes.json`. The probe builds a deterministic synthetic raw
input tree, calls the source discovery helper repeatedly, validates the file count
and ordering, and reports:

- `elapsed_ms_mean` / `elapsed_ms_min` / `elapsed_ms_p95` for source discovery;
- `file_count_mean` as an informational workload-size guard.

The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries. This is a Python-only slice and is locally verifiable on
Linux; GitHub Actions PR-scoped performance remains the merge gate for the
registered probe report.

## Validation Plan

1. Run the registered focused test command locally on Linux.
2. Run the registered changed-scope coverage command and require at least 95%
   coverage for the touched scope.
3. Run the registered probe locally against `origin/main` and this branch, then
   compare `elapsed_ms_mean`.
4. Push only if behavior tests pass and the local probe is neutral-to-improved;
   rely on CI for final registered probe validation before merging.
