# Multimodal Fast-Path Signature Top-Level Key Cache

## Goal

Avoid per-call sorting of the fixed top-level model metadata keys used by `fast_path_probe_signature(...)` while preserving the existing stable signature representation.

## Scope

- `services/mlx-worker-python/worker/runtime/multimodal_fast_paths.py`
- `services/mlx-worker-python/tests/test_multimodal_fast_paths.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/multimodal_fast_path_signature_probe.py`

## Linux-only constraint

This is a Python runtime helper slice and can be verified on Linux with focused pytest, changed-scope coverage, and a local performance probe.

## Performance probe

Register `multimodal-fast-path-signature-top-level-key-cache` in the PR-scoped performance registry. The probe repeatedly calls `fast_path_probe_signature(...)` against a representative loaded VLM model dictionary and prepared vision request, recording:

- `elapsed_ms_mean` (lower is better)
- `peak_bytes_mean` (lower is better)
- `sample_count`

## Success metrics

- Focused tests pass.
- Changed executable line coverage for the touched Python scope is at least 95%.
- Local probe shows behavior-preserving concrete timing/allocation metrics against `origin/main`.
- `git diff --check` passes.
