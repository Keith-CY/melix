# Dataset Split Prefix Cache

## Goal

Reduce repeated short string allocation in `worker.dataset_registry.catalog._path_matches_split(...)` when a selected dataset split is compared against many candidate relative paths.

## Scope

This slice is Python-only and limited to `services/mlx-worker-python/worker/dataset_registry/catalog.py`. It does not change dataset discovery semantics, row parsing, pyarrow behavior, generated protocol artifacts, or Swift/macOS runtime behavior.

## Registered Probe

Registered PR-scoped probe: `dataset-registry-limited-read-streaming` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and exercises `_path_matches_split(...)` over a synthetic 20k-path set. Relevant metrics:

- `elapsed_ms_mean` — lower is better.
- `path_constructor_calls_mean` — lower is better and should remain zero.
- `peak_bytes_mean` — informational allocation signal.

## Implementation Plan

1. Keep the existing `_path_matches_split(...)` behavior intact.
2. Cache the selected split's normalized value plus dash and underscore prefixes across repeated calls, so the common split-filter scan path avoids rebuilding identical short strings for every candidate path.
3. Reuse the existing focused dataset registry tests and registered probe for behavior and performance validation.

## Success Criteria

- Focused dataset registry tests pass.
- Changed-scope coverage for the touched path is at least 95%.
- The registered local probe shows a clear direction for `elapsed_ms_mean` without increasing `path_constructor_calls_mean`.
- `git diff --check` passes.
