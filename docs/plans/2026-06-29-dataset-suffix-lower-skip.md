# Dataset suffix lowercase skip performance slice

## Context

Dataset preview scans skip large numbers of unsupported lowercase sidecar files before yielding supported dataset files. The registered `dataset-registry-preview-limit-short-circuit` PR-scoped probe covers this path through `services/mlx-worker-python/worker/dataset_registry/catalog.py`, focused dataset-registry tests, changed-scope coverage, and the preview/limit probe commands.

## Slice

Avoid calling `str.lower()` for already-lowercase unsupported suffixes in dataset-file suffix classifiers. Supported lowercase suffixes still resolve through the exact dictionary lookup, mixed/uppercase supported suffixes still use the existing lowercase fallback, and unsupported lowercase sidecar files now return immediately.

## Verification

- Focused tests: dataset-registry preview-limit registered `test_command`.
- Changed-scope coverage: dataset-registry preview-limit registered `coverage_command`.
- Performance: dataset-registry preview-limit registered `probe_command`, plus local before/after sidecar-heavy samples on Linux.

## Scope Boundary

This is a Python-only Linux-verifiable slice. It does not change dataset traversal order, row parsing behavior, or Swift runtime behavior.
