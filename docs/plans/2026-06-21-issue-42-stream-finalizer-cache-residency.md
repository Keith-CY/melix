# Issue 42 Stream Finalizer Cache Residency

## Source

- GitHub issue: <https://github.com/Keith-CY/melix/issues/42>
- Governing roadmap: `docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md`
- Related unit: Unit 2.3.3, VLM stream/cache lifecycle tests for unload, cache-hit replay, failure, and cancellation.
- Prior slice: PR #2212, request-owned runtime leases and pending unload receipts.

## Goal

Keep normal multimodal stream finalization from evicting reusable VLM cache
state. Request finalizers should close per-request stream and temporary media
resources only. Process-wide cache cleanup belongs behind explicit unload,
memory-pressure, or operator-requested cleanup paths with receipts.

This slice locks the worker-owned contract for deterministic VLM streams before
promoting broader VLM fast paths. It does not claim throughput improvement.

## Architecture

`EngineCore.generate()` already owns a `StreamLifetimeLease` per streamed
generation and releases it from the generator `finally` block. The VLM runtime
owns media preparation, cache identity, cache residency, and temp-media
cleanup. The correct lifecycle boundary is therefore:

- normal stream drain releases the stream lease and temp media only;
- early client close releases the stream lease and temp media only;
- explicit model unload completes through `WorkerRegistry` unload receipts and
  asks the runtime to drop model-scoped VLM cache state.

The deterministic VLM runtime is the right executable surface for this slice
because it already exposes cache stats and cache-hit receipts without requiring
real MLX hardware or a pinned `mlx-vlm` backend.

## Test Plan

Add worker-level regression coverage that:

1. Opens and fully drains a multimodal `Generate` stream, then proves the VLM
   cache remains resident and the next identical request records a cache hit.
2. Opens a second multimodal stream and closes the generator after the first
   event, then proves the stream lease is released while the VLM cache remains
   resident.
3. Calls explicit model unload after the stream is closed, then proves the
   unload receipt is completed and the runtime cache no longer reports resident
   VLM blocks.

The full stream lifecycle regression lives in
`services/mlx-worker-python/tests/test_vlm_stream_lifecycle.py`.
`services/mlx-worker-python/tests/test_vision_runtime.py` keeps a narrow
deterministic-runtime cache-close assertion that remains covered by the existing
PR-scoped VLM performance focused commands.

## Performance Probes And Success Metrics

- Cache-residency metrics remain stable after normal and early stream close:
  `block_count > 0`, `l1_bytes > 0`, and repeated-request `l1_hit_rate` is
  non-zero.
- Runtime request metrics report no leaked active VLM request after early stream
  close.
- Explicit unload reports completed unload receipt timestamps and reduces VLM
  cache stats to zero resident blocks.
- No protobuf schema change is needed for this slice; unload receipts are
  already surfaced by `UnloadModel` pending/completed receipt state.

## Verification

Required focused checks before PR handoff:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_vlm_stream_lifecycle.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_vlm_stream_lifecycle.py services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_parses_each_image_uri_once services/mlx-worker-python/tests/test_vision_runtime.py::test_vlm_runtime_reuses_cache_for_identical_multimodal_requests services/mlx-worker-python/tests/test_vision_runtime.py::test_cache_service_reports_vlm_cache_state_after_generation`
- Changed-scope coverage for touched Python files must be at least 95 percent
  before commit or PR handoff.

## Non-Goals

- No live VLM performance claim.
- No cache purge API implementation.
- No protobuf schema change.
- No real media-feature store replacement; Unit 3.1 owns real work avoidance.
