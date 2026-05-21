# Dataset Preview Zero-Limit Short-Circuit

## Goal

Avoid unnecessary dataset snapshot file discovery when callers request a preview
with `limit <= 0`. The reader should preserve the existing empty result while
returning before any supported-file scan or row decoder work begins.

## Linux constraint

This is a Python dataset registry slice and is locally verifiable on Linux with
focused pytest, changed-scope coverage, and the registered PR-scoped performance
probe.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`dataset-registry-preview-limit-short-circuit` in
`infra/perf/pr_scoped_probes.json`. This slice extends that probe with explicit
zero-limit metrics while keeping the existing `limit=1` preview metrics:

- `zero_limit_elapsed_ms_mean`
- `zero_limit_peak_bytes_mean`

The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_registry_preview_limit_probe.py`

## Optimization

Return the already-empty row list immediately when `read_hf_dataset_snapshot_rows()`
receives a non-`None` `limit <= 0`. This keeps row-reader semantics unchanged for
zero/negative limits while skipping generator setup, directory traversal, and
first-file probing.

## Success metrics

- Focused dataset registry pytest and PR-scoped probe tests pass.
- Changed-scope coverage for touched executable Python/test/probe files remains
  at least 95%.
- The local registered probe reports lower `zero_limit_elapsed_ms_mean` versus
  the pre-change baseline while preserving `rows_returned`,
  `zero_limit_rows_returned`, and the existing `limit=1` preview metrics.
- GitHub Actions PR-scoped performance completes successfully before merge.
