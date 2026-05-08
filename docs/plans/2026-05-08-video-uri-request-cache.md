# Video URI Request Cache Optimization

## Goal

Reduce repeated URI video preprocessing work when one vision request contains the same URI-backed video part multiple times.

## Scope

- `services/mlx-worker-python/worker/runtime/video_preprocessing.py`
- `services/mlx-worker-python/worker/runtime/multimodal_preprocessing.py`
- focused tests for video preprocessing and the vision-request cache handoff
- `scripts/video_preprocessing_uri_probe.py`
- the existing `video-preprocessing-uri-byte-length-reuse` PR-scoped performance probe entry

## Linux-only constraint

This is a Python worker optimization and can be verified on Linux with focused pytest, changed-scope coverage, and the existing command-json PR-scoped performance probe.

## Performance probe

Use the existing registered probe ID: `video-preprocessing-uri-byte-length-reuse`.

The probe repeatedly prepares the same URI-backed video part and records:

- `elapsed_ms_mean` (lower is better)
- `byte_length_getattrs_per_call` (structural guard; must stay one metadata read per call)

## Success metrics

- Focused pytest passes.
- Changed-scope automated coverage is at least 95% for touched executable Python scope.
- Local probe shows lower `elapsed_ms_mean` against `origin/main` while preserving structural metadata-read behavior.
- `git diff --check` passes.
