# Multimodal Fast-Path Signature Metadata Ordering Optimization

## Goal

Reduce redundant work in `fast_path_probe_signature(...)` by avoiding iteration and sorting of arbitrary nested metadata dictionaries when the signature only accepts a fixed small metadata-key set.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python` and can be verified on Linux with focused pytest, changed-scope coverage, and the existing PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/runtime/multimodal_fast_paths.py`
- `services/mlx-worker-python/tests/test_multimodal_fast_paths.py`
- `docs/plans/2026-05-05-multimodal-fast-path-signature-metadata-order.md`

## Performance probe

Use the existing registered PR-scoped probe:

- Probe ID: `multimodal-fast-path-signature-top-level-key-cache`
- Script: `scripts/multimodal_fast_path_signature_probe.py`
- Primary metric: `elapsed_ms_mean` lower is better
- Secondary metric: `peak_bytes_mean` informational

## Success metrics

- Preserve exact signature tuple output and nested metadata precedence.
- Focused pytest passes for multimodal fast-path signature behavior and scoped-probe registry tests.
- Changed-scope coverage is at least 95% for touched executable Python scope.
- Local probe shows lower `elapsed_ms_mean` versus an `origin/main` worktree on the same workload.
