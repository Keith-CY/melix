# P6-M4 Audio Routing and Endpoint Surface

**Phase:** Phase 6, `P6-M4`
**Goal:** Expose live control-plane audio routes for transcription and speech, wire the Python bridge through the non-text worker client surface, and make Phase 6 audio models visible from the default local stack.
**Scope:** Swift control plane, Python bridge helper, local stack bootstrap, integration tests, and metrics for `/v1/audio/transcriptions` and `/v1/audio/speech`.

## Non-Goals

- No native Chat panel work yet.
- No additional desktop operator UI work yet.
- No real MLX speech backend integration; deterministic worker runtimes from `P6-M3` remain the default verification path.
- No multimodal scheduling isolation or background-lane pressure policy work yet.

## Context

- Canonical phase plan: `docs/plans/2026-03-27-phase-6-vision-ocr-audio-transcription.md`
- Milestone ladder: `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
- Prior milestone: `docs/plans/2026-03-29-p6-m3-audio-runtime.md`

`P6-M3` landed deterministic worker-side transcription and speech runtimes, but the control plane still lacked:

- non-text bridge methods for `Transcribe` and `Speak`
- public HTTP routes for audio transcription and speech synthesis
- audio route readiness in `/health`
- phase-6 model seeding and preload in the default local stack

This milestone closes that gap without expanding into desktop UX or multimodal scheduling policy.

## Assumptions And Defaults

- Audio transcription requests use JSON only in this milestone and accept inline base64 audio or a local file URI.
- Speech synthesis requests use JSON input and return raw audio bytes with an audio content type.
- The default local stack should seed Phase 6 multimodal models and preload deterministic Python worker models needed for live endpoint verification.
- Metrics must be non-`N/A` for control-plane request latency and speech output size on the changed path.

## Performance Probes

- `audio.transcription_request_latency_ms`
- `audio.seconds_processed_per_second`
- `audio.speech_request_latency_ms`
- `audio.speech_output_bytes`
- `/health` route readiness for `python_transcription`
- `/health` route readiness for `python_speech`

## Work Plan

### Task 1: Extend the non-text worker bridge for audio RPCs

Add `Transcribe` and `Speak` to the Swift-side non-text worker client protocol and bridge command vocabulary, then wire the Python helper process to the gRPC inference service methods.

**Areas:**
- `services/control-plane-swift/Sources/WorkerClient/`
- `services/mlx-worker-python/worker/control_plane_bridge.py`

**Acceptance:**
- Bridge unit tests decode unary transcription and speech payloads.
- Audio bridge failures surface as `worker_unavailable`.

### Task 2: Add public audio endpoints to the HTTP gateway

Expose:

- `POST /v1/audio/transcriptions`
- `POST /v1/audio/speech`

Map them to the Python non-text worker routes, return stable JSON for transcription, raw audio bytes for speech, and emit request metrics.

**Areas:**
- `services/control-plane-swift/Sources/HTTPGateway/OpenAI/`
- `services/control-plane-swift/Tests/HTTPGatewayTests/`

**Acceptance:**
- Audio endpoint tests cover success and route selection.
- `/health` includes `python_transcription` and `python_speech`.

### Task 3: Update default stack model visibility and preload

Switch the control-plane bootstrap to seed the Phase 6 contract model catalog and preload the Phase 6 Python runtime slice needed for audio endpoint verification.

**Areas:**
- `services/control-plane-swift/Sources/Bootstrap/`
- `services/control-plane-swift/Sources/WorkerClient/`

**Acceptance:**
- `/v1/models` exposes Phase 6 multimodal model IDs in the live stack.
- Audio models have dispatch handles in the local dev stack before requests arrive.

### Task 4: Integration and metrics evidence

Add live-stack integration tests for both audio endpoints and record concrete deterministic latency/output metrics.

**Commands:**
- `swift test --package-path services/control-plane-swift --filter PythonBridgeWorkerClientTests`
- `swift test --package-path services/control-plane-swift --filter OpenAIHandlerTests`
- `UV_CACHE_DIR=.runtime/uv-cache make py-test`
- `UV_CACHE_DIR=.runtime/uv-cache make integration-test`
- `make swift-test`
- `make coverage`

**Acceptance:**
- Live integration covers transcription and speech successfully.
- Touched scope coverage remains at least `95%`.
- Metrics report includes concrete audio endpoint values.

## Rollback / Safe Exit

- If the HTTP endpoint mapping destabilizes the gateway, keep the bridge methods and audio preload, then return `404` for the public routes again while preserving worker-side audio support.
- If raw speech bytes prove incompatible with later API expectations, keep the worker RPC and swap only the HTTP response shaping in a follow-up milestone.
