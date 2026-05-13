# Multimodal Preprocessing URI Parse Elision

## Goal

Reduce redundant URI parsing in the Python multimodal preprocessing path for local image URI inputs.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python` and can be verified on Linux with focused pytest, changed-scope coverage, and a synthetic local performance probe.

## Touched files

- `services/mlx-worker-python/worker/runtime/multimodal_preprocessing.py`
- `services/mlx-worker-python/tests/test_vision_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/multimodal_preprocessing_uri_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Probe definition

Register `multimodal-preprocessing-local-uri-parse-elision` in the PR-scoped performance registry.

The probe repeatedly prepares a vision request with a local `file://` image URI and records:

- `elapsed_ms_mean` — lower is better
- `urlparse_calls_mean` — lower is better and should drop from two parses per local URI to one parse per local URI
- `iteration_count` and `sample_count` — workload shape

## Success metrics

- Focused pytest for the touched scope passes.
- Changed-scope coverage for touched executable Python files is at least 95%.
- The local probe reports `urlparse_calls_mean == iteration_count` on the optimized branch.
- `git diff --check` passes.

## 2026-05-13 follow-up slice

The plain local `file://` path now skips `urllib.parse.unquote(...)` when the parsed path contains no percent escapes, while percent-encoded file paths still decode through the existing helper. This keeps the registered `multimodal-preprocessing-image-uri-single-parse` / local URI probe coverage on the affected preprocessing path and narrows the per-image URI hot path without changing remote URL handling.
