# P6-M6 Isolation and Observability

## Goal

Land the Phase 6 isolation slice by making OCR, VLM, transcription, and speech visible as explicit background workloads with measurable pressure, queue, and text-protection signals.

## Scope

- add dedicated multimodal background lanes to the control-plane scheduler read model
- track active multimodal work separately from interactive text work
- expose worker-side multimodal probe snapshots through runtime stats
- record preprocessing latency, preprocessing peak memory, and modality-specific latency metrics in the control plane
- publish text-protection metrics when interactive text executes under concurrent multimodal load

## Non-Goals

- add new public endpoints
- change OCR, VLM, transcription, or speech response payload shapes
- add image generation or image editing
- implement the final Phase 6 operator evidence runbook bundle that belongs to `P6-M7`

## Files

- Modify: `packages/protocol/schema/worker/v1/runtime.proto`
- Regenerate: `packages/protocol/swift/**/*`
- Regenerate: `packages/protocol/python/**/*`
- Modify: `services/control-plane-swift/Sources/EnginePool/SchedulerReadModel.swift`
- Modify: `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
- Modify: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- Modify: `services/control-plane-swift/Sources/WorkerClient/WorkerClient.swift`
- Modify: `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- Modify: `services/control-plane-swift/Sources/WorkerClient/WorkerRoute.swift`
- Modify: `services/mlx-worker-python/worker/registry.py`
- Modify: `services/mlx-worker-python/worker/engine/engine_core.py`
- Modify: `services/mlx-worker-python/worker/engine/transcription_core.py`
- Modify: `services/mlx-worker-python/worker/engine/speech_core.py`
- Modify tests under `services/control-plane-swift/Tests`
- Modify tests under `services/mlx-worker-python/tests`
- Modify: `docs/README.md`

## Implementation Notes

1. Extend worker runtime stats with a Melix-native multimodal probe summary rather than adding endpoint-specific response fields.
2. Keep the scheduler read model as the source of lane and queue truth, but allow concurrent active requests so multimodal background work can coexist with interactive text.
3. Route OCR and VLM chat traffic into explicit multimodal background lanes from the request coordinator.
4. Wrap audio transcription and speech endpoint execution with scheduler queue/admit/finish bookkeeping so those requests participate in the same isolation metrics.
5. Record `scheduler.text_ttft_under_multimodal_ms` only when a text request reaches first token while any multimodal background request is active.

## Required Metrics

- `scheduler.multimodal_active_requests`
- `scheduler.multimodal_queued_requests`
- `scheduler.multimodal_queue_delay_ms`
- `scheduler.multimodal_backpressure`
- `scheduler.text_protection_active`
- `scheduler.text_ttft_under_multimodal_ms`
- `vision.preprocess_latency_ms`
- `vision.preprocess_peak_memory_bytes`
- `vision.ocr_latency_ms`
- `vision.vlm_first_token_ms`
- `audio.preprocess_latency_ms`
- `audio.preprocess_peak_memory_bytes`
- `audio.transcription_latency_ms`
- `audio.speech_latency_ms`

## Verification

```bash
make proto
make swift-test
make py-test
make integration-test
make coverage
```

## Acceptance

- queue snapshots include multimodal background lanes
- OCR, VLM, transcription, and speech update scheduler and metrics state without being misclassified as interactive text
- interactive text records dedicated TTFT evidence when multimodal background traffic is active
- touched-scope automated coverage remains at or above `95%`
