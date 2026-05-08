# Deterministic Image Output Byte-Length Reuse

## Context

The deterministic image generation runtime emits metadata and probe snapshots for
synthetic image artifacts. The PR-scoped probe
`deterministic-image-output-byte-accounting` already covers this path and checks
that output byte accounting does not rescan generated images.

## Slice

Reuse the generated payload byte length inside the `generate_images` and `edit_image`
artifact loops instead of calling `len(payload)` separately for artifact metadata
and aggregate output byte accounting. The shared artifact metadata helper accepts
an already-known payload byte length so edit-generated artifacts do not re-read
the payload length after the loop has already accounted for output bytes.

## Scope

- `services/mlx-worker-python/worker/runtime/deterministic_image_generation_runtime.py`
- Existing focused image runtime tests and the registered PR-scoped performance
  probe for deterministic image output byte accounting.

## Verification Plan

Run locally on Linux:

1. Focused pytest for the deterministic image output accounting behavior and
   registered probe dispatch coverage.
2. Changed-scope coverage for the touched runtime, tests, registered probe test,
   and probe script.
3. Registered probe command before and after the change to compare metrics.

The expected behavioral result is unchanged generated artifact metadata and
probe output bytes. The expected performance result is neutral-to-lower elapsed
probe time while `output_byte_scan_calls_mean` remains `0.0`.
