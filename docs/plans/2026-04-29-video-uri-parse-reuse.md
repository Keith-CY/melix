# Video URI Parse Reuse Optimization Plan

## Goal

Reduce redundant URI parsing work in the Python video preprocessing path under `services/mlx-worker-python` without changing accepted input contracts or output fields.

## Scope

- `services/mlx-worker-python/worker/runtime/video_preprocessing.py`
- `services/mlx-worker-python/tests/test_video_preprocessing.py`

## Linux-Only Constraint

This slice must stay Python-only and locally verifiable on Linux. No Swift or macOS-only behavior is in scope.

## Proposed Change

Introduce a small internal parsed-reference helper so `prepare_video_input()` can parse and decode a URI reference once, then reuse that normalized result for:

- URI scheme validation
- format inference from path suffix
- filename inference from path name

## Safety Constraints

- Preserve supported schemes exactly.
- Preserve format inference and filename inference behavior exactly.
- Preserve URI identity hashing inputs exactly.
- Keep the change small and reviewable.

## Tests

Add focused tests covering:

- encoded remote URI filename/format inference
- encoded `file://` URI filename/format inference
- existing invalid-contract behavior remains unchanged

## Performance Probe

Run a micro-benchmark that compares repeated baseline-style URI parsing against the helper-based single-parse path over a representative encoded HTTP URI.

Example probe target:
- URI: `https://example.com/media/demo%20clip.mov?token=abc`
- Loop count: large enough to measure stable timings

## Success Metrics

- Targeted pytest for touched scope passes.
- Changed executable file coverage is at least 95%.
- Performance probe shows lower wall-clock time for the parse-heavy loop.
- `git diff --check` passes.
