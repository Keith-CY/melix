# Issue 40 Cache Residency Lease Hardening

## Goal

Implement the latest issue #40 cache/residency hardening slice by giving request-owned runtime state an explicit lease boundary and making unload attempts observable when they are blocked by active work.

## Context

Issue #40 was closed by PR #1710 with the main runtime cache reuse milestone. Later watch notes added smaller hardening slices. This plan covers the 2026-06-19 watch finding:

- request-owned runtime state needs explicit lifetime boundaries
- destructive unload must be refused while an endpoint lease or scheduler request is active
- pending unload receipts must report `abort_requested`, `pending_unload`, `released_at`, and `unloaded_at`

## Architecture

Add registry-owned lease accounting keyed by loaded-model handle. Main response paths acquire a request/stream lifetime lease before using `runtime_model` and release it in `finally`. `UnloadModel` will no longer close a model while active leases exist; it records a pending unload receipt, optionally requests abort when `force=true`, and completes the unload automatically when the final lease is released.

The implementation intentionally keeps this as a worker-runtime contract instead of changing public HTTP API shape. Existing proto response fields are sufficient because `UnloadModelResponse.error.details` can carry the pending receipt when unload is refused or deferred.

## Files

- Modify `services/mlx-worker-python/worker/registry.py`
  - add `RequestRuntimeLease`, `StreamLifetimeLease`, and `ModelUnloadReceipt`
  - track active leases by model handle
  - add `acquire_request_runtime_lease`
  - add `request_model_unload`
  - complete pending unload on final lease release
- Modify `services/mlx-worker-python/worker/engine/engine_core.py`
  - wrap text generation with `StreamLifetimeLease`
- Modify `services/mlx-worker-python/worker/engine/speech_core.py`
  - wrap streaming speech with `StreamLifetimeLease`
  - wrap non-streaming speech with `RequestRuntimeLease`
- Modify `services/mlx-worker-python/worker/engine/transcription_core.py`
  - wrap non-streaming transcription with `RequestRuntimeLease`
- Modify `services/mlx-worker-python/worker/engine/image_generation_core.py`
  - wrap image generation with `RequestRuntimeLease`
- Modify `services/mlx-worker-python/worker/engine/image_edit_core.py`
  - wrap image editing with `RequestRuntimeLease`
- Modify `services/mlx-worker-python/worker/grpc_server.py`
  - use `request_model_unload` so busy/pending/not-found outcomes are distinguishable
- Modify `services/mlx-worker-python/tests/test_runtime_edges.py`
  - add registry tests for pending unload receipts and automatic unload after lease release
  - add service-level coverage for active-request unload refusal

## Behavioral Contract

- Acquiring a lease increments the existing active-request counters and pins the loaded model against unload.
- Releasing a lease decrements counters and, if a pending unload exists and no leases remain, closes the runtime model and removes residency accounting.
- `request_model_unload(handle, force=false)`:
  - unknown handle: `found=false`, `unloaded=false`, `pending_unload=false`
  - no active lease: closes immediately, `unloaded=true`, `unloaded_at` set
  - active lease: leaves the model loaded, `pending_unload=true`, `released_at=""`, `unloaded_at=""`
- `request_model_unload(handle, force=true)` additionally sets `abort_requested=true` and signals cancel events for active requests on that handle.
- `UnloadModel` returns `ok=false` with a retriable `unload_pending` error while a lease blocks destructive unload. Error details include the pending receipt fields.

## Tests

1. Add a failing registry test proving an active lease blocks unload, records pending receipt fields, and keeps `model_resident_bytes` non-zero.
2. Add a failing registry test proving `force=true` requests abort for active requests and automatic close happens when the lease is released.
3. Add a failing service test proving gRPC `UnloadModel` distinguishes `unload_pending` from `not_found`.
4. Run the focused Python tests:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest \
  services/mlx-worker-python/tests/test_runtime_edges.py \
  services/mlx-worker-python/tests/test_runtime_service.py \
  -q
```

## Metrics

- Coverage: changed Python lines in `worker/registry.py`, the touched endpoint cores, and `worker/grpc_server.py` must be at least 95%.
- Runtime safety: active leases must keep `runtime_stats().model_resident_bytes` non-zero until the final release.
- Receipt quality: pending unload details must include `abort_requested`, `pending_unload`, `released_at`, and `unloaded_at`.

## Out of Scope

- Reworking all benchmark/evaluation helper paths in this slice.
- Adding new proto fields for lease receipts.
- Implementing disk cache snapshot persistence or cache compression.
- Claiming new issue #40 TTFT wins; this is a safety/residency hardening slice.
