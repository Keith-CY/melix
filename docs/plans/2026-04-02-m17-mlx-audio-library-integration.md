# M17 MLX Audio Library Integration

## Goal

Integrate `mlx-audio` into Melix as an internal Python worker adapter for speech-to-text and text-to-speech while keeping the Melix control-plane API surface unchanged.

## Scope

- route transcription and speech models through `melix.audio.backend_id`
- preserve deterministic development audio models as the default contract harness
- add lazy-loaded `mlx-audio` adapters for STT and TTS inside the Python worker
- project backend metadata through model catalog and control-plane summaries
- extend existing audio probes with backend load and fallback counters
- gate `mlx-audio` behind optional worker dependency profiles

## Non-Goals

- no `mlx_audio.server`, FastAPI routes, or bundled upstream web UI
- no speech-to-speech support in this slice
- no dynamic `mlx-audio` family discovery or automatic remapping
- no new public HTTP routes, protobuf route classes, or capability enums

## Files

- update `services/mlx-worker-python/worker/registry.py`
- add `services/mlx-worker-python/worker/runtime/audio_runtime_protocols.py`
- add `services/mlx-worker-python/worker/runtime/mlx_audio_runtime.py`
- update `services/mlx-worker-python/worker/engine/`
- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `services/mlx-worker-python/worker/grpc_server.py`
- update `services/mlx-worker-python/pyproject.toml`
- update `packages/protocol/schema/worker/v1/runtime.proto`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/HTTPGateway/OpenAI/`
- update `services/control-plane-swift/Sources/WorkerClient/`

## Implementation Notes

- Worker audio runtime selection must remain metadata-driven and must not silently fall back from a real backend to the deterministic backend.
- `mlx-audio` imports must stay inside adapter load paths so the worker can still start without audio extras installed.
- Real STT requests may stage inline audio bytes to a worker-local temporary file, but the temporary file lifecycle stays adapter-local.
- Real TTS requests are model-aware: format validation happens before the worker request is dispatched and the first implementation only accepts `wav`.
- Runtime probes must keep the existing Phase 6 keys stable and add new counters only as additional fields.
- `backend_id` and `family_id` remain model metadata dimensions, not metric-name suffixes.
- Optional dependency profiles must keep default worker installs audio-free and surface dependency problems only when a real audio backend is selected.

## Metrics

- baseline: deterministic transcription and speech latency
- cold load: model load latency for real `mlx-audio` backends
- warm request: request latency after model load
- failure visibility: backend unavailable, voice fallback, and language fallback counters

## Verification

- `make proto`
- `make py-test`
- `make swift-test`
- `make integration-test`
- `make coverage`

## Acceptance

- deterministic development audio endpoints remain unchanged
- real STT and TTS models are routed through backend metadata and exposed through the existing Melix endpoints
- unsupported speech output formats are rejected before worker dispatch
- missing optional dependencies produce structured worker errors instead of crashes
- catalog metadata is stable enough for control-plane and operator surfaces
