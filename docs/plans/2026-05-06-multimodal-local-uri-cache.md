# Multimodal Local URI Cache Optimization

## Goal

Avoid redundant local image file reads when a single vision request references the same local image URI more than once, while preserving per-part media metadata overrides and remote-fetch semantics.

## Linux-only constraint

This is a Python worker slice and can be verified locally on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/runtime/multimodal_preprocessing.py`
- `services/mlx-worker-python/tests/test_vision_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/multimodal_preprocessing_uri_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Performance probe

Registered probe: `multimodal-preprocessing-local-uri-parse-elision`.

The probe now exercises a duplicate local image URI in one `prepare_vision_request(...)` call and records:

- `elapsed_ms_mean` — lower is better
- `urlparse_calls_mean` — structural call count
- `read_bytes_calls_mean` — lower is better; duplicate local URI reads should collapse from two reads per request to one

## Success metrics

- Focused pytest passes for the touched behavior and scoped performance registry smoke tests.
- Changed-scope coverage is at least 95% for touched executable Python scope.
- Local probe shows `read_bytes_calls_mean == iteration_count` for two image parts per request, proving one local file read per duplicate-URI request instead of one read per image part.
