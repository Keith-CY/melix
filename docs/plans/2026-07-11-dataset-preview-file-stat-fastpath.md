# Dataset preview limit-one direct return fast path

## Scope

This Python-only performance slice is limited to the limit-one preview path in
`services/mlx-worker-python/worker/dataset_registry/catalog.py`. It keeps dataset
preview behavior unchanged while returning the first file's limited rows directly
when `read_hf_dataset_snapshot_rows(..., limit=1)` has no split filter, avoiding
the generic multi-file accumulator loop for the common preview case.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`dataset-registry-preview-limit-short-circuit` in
`infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`,
`coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_registry_preview_limit_probe.py`

The probe measures single-row and multi-row preview latency and allocation on a
synthetic snapshot with many ignored sidecars and many supported JSONL files.

## Implementation plan

1. Add/keep regression coverage proving the limit-one preview path bypasses the
   generic limited-file iterator and returns the first file's limited row list
   directly.
2. In `read_hf_dataset_snapshot_rows(...)`, route no-split `limit == 1` requests
   through `_first_supported_dataset_file(...)` and `_read_rows_from_file(...)`
   before constructing the generic accumulator loop.
3. Run the registered focused tests, changed-scope coverage, and local registered
   probe on Linux before opening the PR.
4. Use the GitHub PR-scoped performance workflow as the merge gate.

## Success metrics

- Focused dataset-registry tests pass.
- Changed-scope coverage remains at least 95% for the touched scope.
- The registered probe shows lower or non-regressed `elapsed_ms_mean` and
  `multi_limit_elapsed_ms_mean`, with unchanged `multi_limit_dataset_files_yielded_mean`.
- This slice has no Swift runtime effect; local Linux verification is sufficient
  for the Python path, and GitHub Actions remains the registered probe merge gate.
