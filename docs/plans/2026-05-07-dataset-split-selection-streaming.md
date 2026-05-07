# Dataset Split Selection Streaming

## Goal

Reduce temporary list materialization in `worker.dataset_registry.catalog._selected_dataset_files(...)` when callers request a specific split from a large local Hugging Face dataset snapshot.

## Linux-only constraint

This is a Python-only slice under `services/mlx-worker-python`, so it can be validated on Linux with focused pytest, changed-scope coverage, and a synthetic local performance probe.

## Touched files

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `docs/plans/2026-05-07-dataset-split-selection-streaming.md`

## Implementation plan

1. Normalize the requested split before collecting files.
2. For split-specific reads, stream the supported dataset file iterator once and append only matching non-README files.
3. Preserve the existing all-files tuple behavior for unsplit reads.
4. Add focused regression coverage for split matching order, README filtering, missing-split behavior, and non-split all-file behavior.

## Performance probe

Use a synthetic monkeypatched iterator that yields a large tuple of dataset paths under a temporary snapshot root and measures `_selected_dataset_files(snapshot, split="validation")` with `tracemalloc`.

Success metric: selected rows and ordering are identical while split-specific selection reduces elapsed time and peak traced allocation versus `origin/main`.

## Verification commands

- Focused pytest for dataset registry split selection tests.
- `coverage run` + `scripts/changed_scope_coverage.py` over the changed catalog/test scope, requiring at least 95% changed executable coverage.
- Local `origin/main` vs head split-selection performance probe.
- `git diff --check`.

## PR-scoped CI probe

Changes to `catalog.py` and `test_dataset_registry.py` select the existing dataset registry scoped probes:

- `dataset-registry-limited-read-streaming`
- `dataset-registry-snapshot-inference-single-pass`
- `dataset-registry-preview-limit-short-circuit`

The local probe records the new split-selection hot path explicitly; hosted `pr-scoped-performance` remains the merge gate for the registered dataset-registry scope.
