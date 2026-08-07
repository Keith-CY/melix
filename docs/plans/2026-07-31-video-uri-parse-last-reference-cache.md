# Video preprocessing last-reference parse cache

## Context

The registered `video-preprocessing-uri-byte-length-reuse` PR-scoped probe covers
`services/mlx-worker-python/worker/runtime/video_preprocessing.py` with focused
tests, changed-scope coverage, and `scripts/video_preprocessing_uri_probe.py`.
The probe repeatedly prepares the same remote video URI and measures elapsed time,
metadata `byte_length` reads, and parse calls per prepared input.

## Slice

Add a single last-reference cache around parsed video URI metadata for the URI
preprocessing path. `_parse_video_reference()` already has an LRU cache, but hot
loops still call the wrapper for identical consecutive references. This slice
keeps behavior unchanged while bypassing that wrapper call for repeated URI
inputs in `prepare_video_input()`.

## Verification Plan

1. Add/update a focused regression test showing repeated `prepare_video_input()`
   calls for the same URI reuse parsed metadata while a different URI still
   refreshes the cache.
2. Run the registered focused test command for
   `video-preprocessing-uri-byte-length-reuse`.
3. Run the registered changed-scope coverage command for the same probe.
4. Run `scripts/video_preprocessing_uri_probe.py` locally on Linux and compare
   baseline vs optimized metrics.

## Metrics

Success criteria: behavior tests pass; changed-scope coverage remains at least
95%; the registered probe should reduce `parse_calls_per_call` from one wrapper
call per prepare to near zero for repeated identical URI inputs, with elapsed
mean non-regressing within normal local variance.
