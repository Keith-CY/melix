# Dataset Split Selection Streaming

## Goal

Reduce temporary tuple/list materialization and redundant split matching when `worker.dataset_registry.catalog.read_hf_dataset_snapshot_rows(...)` previews a specific split from a large local Hugging Face dataset snapshot with a row limit.

## Linux-only constraint

This is a Python-only slice under `services/mlx-worker-python`, so it can be validated on Linux with focused pytest, changed-scope coverage, and a synthetic local performance probe.

## Touched files

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `docs/plans/2026-05-07-dataset-split-selection-streaming.md`

## Implementation plan

1. Keep `_selected_dataset_files(...)` behavior-compatible for direct callers by returning a tuple in deterministic order.
2. Add a lazy split-matching iterator that skips README metadata and yields matching supported files one at a time.
3. Route split-specific row reads through the lazy iterator so `limit=1` can stop before scanning later split files once the requested row budget is satisfied.
4. Preserve full-scan behavior for missing splits because the reader must prove there are no matches before returning an empty result.
5. Add focused regression coverage for positive split-limit short-circuiting, existing missing-split behavior, and direct selection ordering.

## Performance probe

Use a synthetic monkeypatched iterator that yields many validation files under a temporary snapshot root and measures `read_hf_dataset_snapshot_rows(snapshot, split="validation", limit=1)`, including elapsed time, peak traced allocation, and the number of supported paths considered before the row limit is satisfied.

Success metric: parsed rows are identical while the head branch considers only the first matching file for a limited split preview; `origin/main` scans/materializes every matching split file before reading.

## Verification commands

- Focused pytest for dataset registry split selection tests.
- `coverage run` + `scripts/changed_scope_coverage.py` over the changed catalog/test scope, requiring at least 95% changed executable coverage.
- Local `origin/main` vs head split-limit performance probe.
- `git diff --check`.

## PR-scoped CI probe

Changes to `catalog.py` and `test_dataset_registry.py` select the existing dataset registry scoped probes:

- `dataset-registry-limited-read-streaming`
- `dataset-registry-snapshot-inference-single-pass`
- `dataset-registry-preview-limit-short-circuit`

The local probe records the new split-limit hot path explicitly; hosted `pr-scoped-performance` remains the merge gate for the registered dataset-registry scope.
