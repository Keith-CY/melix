# P6-M3 Audio Runtime Implementation Plan

**Phase:** Phase 6, `P6-M3`
**Goal:** Add deterministic audio preprocessing plus worker-side transcription and speech runtimes so the Python worker can serve `Transcribe` and `Speak` directly before the control-plane endpoint work lands.
**Scope:** Python worker only. This milestone covers local audio file handling, inline-audio handling, deterministic preprocessing metrics, transcription response mapping, speech response mapping, model visibility, and worker capability flags.

## Non-Goals

- No control-plane `/v1/audio/transcriptions` or `/v1/audio/speech` endpoint work in this milestone.
- No real MLX or external speech backend integration yet.
- No chat-panel or desktop work.
- No multimodal scheduling isolation work; that remains for later Phase 6 milestones.

## Context

- Canonical phase plan: `docs/plans/2026-03-27-phase-6-vision-ocr-audio-transcription.md`
- Milestone ladder: `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
- Prior milestone: `docs/plans/2026-03-29-p6-m2-ocr-vlm-runtime.md`

The worker already supports deterministic OCR and VLM paths through `Generate`. Audio requests already have protobuf contracts and control-plane route vocabulary, but the Python worker still returns structured `unimplemented` responses for `Transcribe` and `Speak`.

## Assumptions And Defaults

- Audio preprocessing accepts inline bytes and local file URIs or local filesystem paths only.
- Deterministic transcription decodes byte payloads as UTF-8 and treats the decoded text as the transcript.
- Deterministic speech emits reproducible synthetic audio bytes derived from input text, requested voice, and requested format.
- Audio duration is estimated deterministically from byte size rather than from real media decoding.
- Metrics must be non-`N/A` for preprocessing latency, estimated duration, and output size.

## Performance Probes

- `audio.preprocess_latency_ms`
- `audio.preprocess_input_bytes`
- `audio.preprocess_peak_memory_bytes`
- `audio.estimated_duration_seconds`
- `audio.chunk_count`
- `audio.transcription_latency_ms`
- `audio.speech_latency_ms`
- `audio.speech_output_bytes`

## Work Plan

### Task 1: Add deterministic audio preprocessing

Create a worker runtime helper that normalizes inline bytes and local file audio inputs, estimates duration, tracks chunk count, and emits stable preprocessing probes.

**Areas:**
- `services/mlx-worker-python/worker/runtime/`
- `services/mlx-worker-python/tests/`

**Acceptance:**
- Missing or unsupported audio sources return structured worker errors.
- Local file URIs and plain local paths are both accepted.
- Preprocessing exposes deterministic probe values.

### Task 2: Add deterministic transcription and speech runtimes

Implement small deterministic runtimes for audio transcription and speech generation.

**Areas:**
- `services/mlx-worker-python/worker/runtime/`
- `services/mlx-worker-python/worker/engine/`

**Acceptance:**
- `Transcribe` returns transcript text, language, and estimated duration.
- `Speak` returns deterministic audio bytes and the requested output format.
- Cancel-free deterministic hot path produces non-`N/A` metrics.

### Task 3: Wire registry, model catalog, and worker services

Add audio model types, capability flags, and runtime routing so the worker advertises the new capability slice coherently.

**Areas:**
- `services/mlx-worker-python/worker/model_registry/`
- `services/mlx-worker-python/worker/registry.py`
- `services/mlx-worker-python/worker/grpc_server.py`
- `services/mlx-worker-python/worker/engine/maintenance_core.py`

**Acceptance:**
- Worker handshake reports transcription and speech support.
- Audio dev models can be loaded through the runtime service.
- Model info reflects audio tasks and modalities.

### Task 4: Verification and metrics

Run focused tests first, then worker and integration suites, and record deterministic audio probes.

**Commands:**
- `UV_CACHE_DIR=.runtime/uv-cache make py-test`
- `UV_CACHE_DIR=.runtime/uv-cache make integration-test`
- `make swift-test`
- targeted Python coverage report for touched worker files

**Acceptance:**
- Touched worker scope coverage is at least `95%`.
- Deterministic transcription and speech metrics are recorded with concrete values.

## Rollback / Safe Exit

- If audio runtime wiring destabilizes unrelated worker paths, keep the preprocessing helpers and tests, then return `unimplemented` again from `Transcribe` and `Speak`.
- If deterministic speech output shape proves too opinionated for later endpoint mapping, keep the runtime boundary and swap only the byte rendering format in a follow-up slice.
