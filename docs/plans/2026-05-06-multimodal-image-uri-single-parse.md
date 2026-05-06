# Multimodal Image URI Single-Parse Optimization

## Goal

Reduce redundant URI parsing in `worker.runtime.multimodal_preprocessing` for image URI inputs while preserving local, file, HTTP/HTTPS, missing-file, and unsupported-scheme behavior.

## Linux-only constraint

This slice is Python-only and runs in `services/mlx-worker-python`, so it can be validated on Linux with focused pytest, changed-scope coverage, and a PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/runtime/multimodal_preprocessing.py`
- `services/mlx-worker-python/tests/test_vision_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/multimodal_image_uri_parse_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Probe

Register `multimodal-preprocessing-image-uri-single-parse` as a command-json PR-scoped probe. The probe builds repeated local file image URI requests, wraps `multimodal_preprocessing.urlparse`, and reports:

- `elapsed_ms_mean` (lower is better)
- `urlparse_calls_mean` (lower is better, structural metric)
- `peak_bytes_mean`
- `prepared_image_count`

## Success metrics

- Behavior remains unchanged for local/file/http URI image inputs and existing failure paths.
- Focused pytest passes.
- Changed executable scope coverage is at least 95%.
- Local probe shows `urlparse_calls_mean` reduced from the legacy two-parses-per-local-URI path to one parse per local URI on the optimized branch.
