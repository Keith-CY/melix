# Multimodal Fast-Path Signature Serialization Cache

## Goal

Avoid materializing intermediate tuple objects before serializing the fixed top-level model metadata and accepted nested metadata pairs used by `fast_path_probe_signature(...)`, while preserving the existing stable tuple-repr-compatible signature strings.

## Scope

- `services/mlx-worker-python/worker/runtime/multimodal_fast_paths.py`
- `services/mlx-worker-python/tests/test_multimodal_fast_paths.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/multimodal_fast_path_signature_probe.py`

## Linux-only constraint

This is a Python runtime helper slice and can be verified on Linux with focused pytest, changed-scope coverage, and a local performance probe.

## Performance probe

Use the registered `multimodal-fast-path-signature-top-level-key-cache` PR-scoped probe. The probe repeatedly calls `fast_path_probe_signature(...)` against a representative loaded VLM model dictionary and prepared vision request, recording:

- `elapsed_ms_mean` (lower is better)
- `peak_bytes_mean` (lower is better)
- `sample_count`

## Success metrics

- Focused tests pass.
- Changed executable line coverage for the touched Python scope is at least 95%.
- Local probe shows behavior-preserving concrete timing/allocation metrics against `origin/main`.
- `git diff --check` passes.
