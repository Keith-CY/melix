# Phase 6 Vision, OCR, Audio, and Chat Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add analysis-style multimodal capabilities to Melix by introducing VLM, OCR, audio transcription, audio speech, and a native Chat panel without destabilizing the text and retrieval surfaces established in earlier phases.

**Architecture:** Melix keeps multimodal analysis and audio generation in the Python worker plane, adds explicit preprocessing and capability routing for image and audio inputs, and keeps the control plane responsible for endpoint translation, admission, and resource isolation. Text remains the interactive priority class while multimodal analysis runs in background lanes and dedicated worker routes. The native SwiftUI desktop app adds a Chat panel only after the backend can expose stable text, tool, reasoning, and multimodal state through the control plane.

**Tech Stack:** Swift 6, Swift Package Manager, Python 3.12, uv, gRPC over Unix Domain Sockets, MLX-backed Python runtimes where applicable, SwiftProtobuf and Python-generated protocol artifacts, XCTest, pytest, integration tests.

---

## Goal

Deliver a production-shaped Phase 6 implementation that adds VLM and OCR request handling plus `POST /v1/audio/transcriptions` and `POST /v1/audio/speech`, with explicit multimodal preprocessing, scheduling isolation from interactive text traffic, and a real native Chat panel.

## Non-Goals

- Add image generation or image editing.
- Move multimodal analysis into the Swift text worker.
- Collapse OCR, VLM, and transcription into one indistinguishable worker type.
- Build the Image panel, HuggingFace workflows, or training tools that belong to later phases.
- Introduce remote media storage or cloud-only preprocessing dependencies.

## Context

- Relevant specs:
  - `docs/architecture-spec.md`
  - `docs/worker-rpc-schema.md`
  - `docs/phase-roadmap.md`
  - `docs/plans/2026-03-27-phase-5-embeddings-rerank.md`
- Relevant code paths:
  - `services/control-plane-swift/Sources/HTTPGateway`
  - `services/control-plane-swift/Sources/WorkerClient`
  - `services/control-plane-swift/Sources/EnginePool`
  - `services/mlx-worker-python/worker/runtime`
  - `services/mlx-worker-python/worker/engine`
  - `services/mlx-worker-python/worker/model_registry`
  - `tests/integration`
- Current constraints:
  - The current request translation path is text-first and has limited multimodal normalization.
  - Input preprocessing for image and audio is not yet modeled as a first-class worker concern.
  - Mixed text and multimodal resource pressure is not yet visible enough for confident routing.

## Assumptions

- Text and retrieval surfaces from earlier phases remain stable and should not be rewritten.
- Multimodal analysis belongs in Python worker classes first because it aligns with the broader worker plane and preprocessing needs.
- Audio transcription and audio speech are the new public audio endpoints added in this phase; image-based analysis remains attached to compatible existing text-style flows or dedicated worker calls beneath the control plane.
- Background-lane isolation is mandatory before multimodal analysis can be considered complete.
- The native Chat panel must remain a control-plane consumer and not become a second execution orchestrator.

## Performance Probes and Metrics

Required probes:

- `audio.transcription_latency_ms`
- `audio.seconds_processed_per_second`
- `vision.ocr_latency_ms`
- `vision.vlm_first_token_ms`
- `vision.preprocess_latency_ms`
- `vision.preprocess_peak_memory_bytes`
- `scheduler.multimodal_queue_delay_ms`
- `scheduler.text_ttft_under_multimodal_ms`
- `audio.speech_latency_ms`
- `desktop.chat_action_latency_ms`

Required comparison report:

- text-only baseline vs text-plus-multimodal load
- OCR vs VLM latency on representative image sizes
- transcription latency by audio duration bucket
- speech synthesis latency by output length bucket

## Work Plan

### Task 1: Finalize multimodal capability typing and request normalization contracts

**Objective**

Make image-input and audio-input workloads explicit in the shared routing and worker capability model.

**Files**

- Modify: `packages/protocol/schema/worker/v1/common.proto`
- Modify: `packages/protocol/schema/worker/v1/runtime.proto`
- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
- Regenerate: `packages/protocol/swift/**/*`
- Regenerate: `packages/protocol/python/**/*`

**Implementation**

- Add capability metadata for OCR, VLM, and transcription worker classes.
- Make preprocessing and media-input identity explicit enough for routing, metrics, and errors.
- Preserve the control-plane contract as the canonical routing and observability source.

**Verification**

- `make proto`

**Acceptance**

- Capability typing can distinguish audio and image analysis workloads cleanly.

### Task 2: Implement Python worker preprocessing and multimodal runtime adapters

**Objective**

Give the Python worker real image and audio preprocessing plus analysis runtimes without turning preprocessing into ad hoc control-plane logic.

**Files**

- Modify: `services/mlx-worker-python/worker/runtime/*`
- Modify: `services/mlx-worker-python/worker/engine/*`
- Modify: `services/mlx-worker-python/worker/model_registry/*`
- Modify tests under `services/mlx-worker-python/tests`

**Implementation**

- Add OCR, VLM, and transcription runtime adapters plus request validation.
- Add explicit preprocessing steps for audio decoding, image loading, resizing, and normalization.
- Keep capability reporting, model lifecycle, and metrics separated by multimodal class.

**Verification**

- `make py-test`

**Acceptance**

- The Python worker can execute OCR, VLM, and transcription requests with clear capability boundaries and test coverage.

### Task 3: Add control-plane routing and the audio endpoints

**Objective**

Expose multimodal analysis and audio generation through the local API surface without weakening existing text endpoints.

**Files**

- Create or modify: `services/control-plane-swift/Sources/HTTPGateway/*`
- Modify: `services/control-plane-swift/Sources/Requests/*`
- Modify: `services/control-plane-swift/Sources/WorkerClient/*`
- Modify tests under `services/control-plane-swift/Tests/HTTPGatewayTests`

**Implementation**

- Add `POST /v1/audio/transcriptions` and `POST /v1/audio/speech`.
- Extend request translation so image and audio inputs can map onto the correct worker classes and request shapes.
- Preserve existing text endpoint behavior while adding multimodal-aware validation and error reporting.

**Verification**

- `make swift-test`

**Acceptance**

- The control plane can expose transcription and route multimodal analysis requests coherently.

### Task 4: Isolate multimodal analysis from interactive text traffic

**Objective**

Make multimodal work a deliberate background class so it cannot silently steal responsiveness from text.

**Files**

- Modify: `services/control-plane-swift/Sources/EnginePool/*`
- Modify: `services/control-plane-swift/Sources/Metrics/*`
- Modify related tests under `services/control-plane-swift/Tests`

**Implementation**

- Route OCR, VLM, and transcription into dedicated lanes or worker pools.
- Add pressure and admission metrics that show how multimodal work affects text TTFT and queue delay.
- Define explicit backpressure behavior when multimodal workers saturate local resources.

**Verification**

- `make swift-test`
- `make integration-test`

**Acceptance**

- Text latency remains within the defined Phase 6 acceptance envelope under multimodal load.

### Task 5: Add the native Chat panel, integration evidence, runbooks, and metrics reporting

**Objective**

Leave Phase 6 with reproducible proof that multimodal analysis is callable, isolated, measurable, and visible through a real native Chat panel.

**Files**

- Create or modify integration tests under `tests/integration`
- Create or modify: `docs/runbooks/*`
- Modify: `README.md`

**Implementation**

- Add integration cases for transcription, speech, OCR, and at least one VLM analysis path.
- Add the native Chat panel on top of existing control-plane state, including tool, reasoning, and multimodal interaction where backend support exists.
- Document local operator workflow for booting multimodal workers and reproducing metrics.
- Standardize the Phase 6 metrics report for preprocessing latency, analysis latency, speech latency, and text interference.

**Verification**

- `make swift-test`
- `make py-test`
- `make integration-test`
- `make coverage`

**Acceptance**

- Integration tests prove endpoint behavior and background-lane isolation.
- The touched scope meets the `>=95%` coverage rule.
- The Phase 6 metrics report contains non-`N/A` multimodal numbers.

## Verification

```bash
make proto
make swift-test
make py-test
make integration-test
make coverage
```

Expected evidence:

- multimodal capability protocol generation succeeds
- Python worker tests cover OCR, VLM, and transcription paths
- control-plane tests cover transcription and multimodal request translation
- integration covers transcription plus image-based analysis behavior
- touched-scope coverage is at least `95%`
- the metrics report includes latency, preprocessing, speech, and text-interference numbers

## Acceptance Criteria

- Melix exposes stable multimodal analysis behavior for OCR, VLM, and audio transcription.
- The control plane routes multimodal work to dedicated worker classes rather than the text engine.
- Background-lane isolation keeps interactive text responsive.
- Operators can reproduce multimodal metrics and integration evidence locally.
- The native Chat panel reflects real runtime, tool, reasoning, and multimodal state through the control plane.
- Phase 6 concludes with reproducible latency, chat-panel, and interference evidence.

## Rollback or Safe Exit

- Land capability typing, Python worker execution, control-plane routing, and interference controls in separate slices.
- Keep new public endpoint work gated behind passing integration tests before considering the phase complete.
- If one multimodal family proves unstable, defer that family explicitly rather than shipping ambiguous capability claims.
