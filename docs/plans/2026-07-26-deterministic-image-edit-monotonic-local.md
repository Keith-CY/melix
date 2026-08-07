# Deterministic Image Edit Monotonic Local Binding

## Context

The deterministic image runtime records job latency and artifact publish latency
for generated and edited image artifacts. The registered PR-scoped probe
`deterministic-image-output-byte-accounting` covers
`services/mlx-worker-python/worker/runtime/deterministic_image_generation_runtime.py`
and includes focused `test_command`, `coverage_command`, and `probe_command`
entries for image generation/edit timing and output-byte accounting.

## Slice

This Python-only performance slice narrows only `edit_image()` timing overhead.
The generation path already binds `time.monotonic` once per call and reuses that
local binding for artifact publish and job latency timing. The edit path still
looked up `time.monotonic` through the module global for the job timer, source
artifact write, optional mask write, every generated artifact write, and final
job latency. Reuse one local monotonic binding through `edit_image()` and pass it
to the write helper while preserving the helper fallback for other callers.

## Scope

- `services/mlx-worker-python/worker/runtime/deterministic_image_generation_runtime.py`
- `services/mlx-worker-python/tests/test_image_runtime.py`
- Existing registered PR-scoped performance probe
  `deterministic-image-output-byte-accounting`

## Verification Plan

Run locally on Linux:

1. Focused pytest for deterministic image output accounting and the new edit
   monotonic-binding regression.
2. Changed-scope coverage for the touched runtime/test files and registered
   probe coverage entries.
3. Registered probe command locally and compare against `origin/main`.

Expected behavior is unchanged artifact metadata, payload bytes, output-byte
accounting, and cancellation semantics. Expected performance is neutral-to-lower
`elapsed_ms_mean`; `output_byte_scan_calls_mean` must remain `0.0`.
