# P6-M1 Multimodal Contracts Implementation Plan

## Goal

Establish the Phase 6 multimodal contract layer so Melix can represent OCR, VLM, transcription, and speech workloads as typed worker capabilities with explicit image and audio input normalization rules.

This milestone must leave the repository able to:

- describe multimodal worker capability families without overloading the existing text-only shapes
- encode image and audio request inputs with stable transport metadata
- express preprocessing hints and media identity for routing, validation, and metrics
- verify multimodal payload normalization before any Phase 6 runtime implementation lands

## Non-Goals

- Do not implement OCR, VLM, transcription, or speech runtime behavior in this milestone.
- Do not add public HTTP handlers for Phase 6 endpoints yet.
- Do not add native Chat panel UI here.
- Do not change scheduler policy or background-lane isolation beyond the representational contract surface.
- Do not add image-generation or image-editing job semantics, which belong to Phase 7.

## Context

Phase 5 already introduced typed capability routing for text, embeddings, rerank, and model operations. The shared worker schema also already has a generic `MessagePart` with inline image and audio payload options, plus worker-side `Transcribe`, `ImageGenerate`, and `ImageEdit` RPC placeholders.

What is missing is the explicit multimodal contract layer for Phase 6:

- OCR and VLM capability typing still collapse into the broad multimodal class.
- Audio transcription and speech output do not yet advertise stable worker capabilities.
- Message-part shapes do not carry normalization metadata such as MIME type, source kind, or preprocessing hints.
- Control-plane request tests do not yet pin accepted image/audio payload shapes before runtime work begins.

Canonical references:

- `docs/architecture-spec.md`
- `docs/plans/2026-03-27-phase-6-vision-ocr-audio-transcription.md`
- `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
- `docs/worker-rpc-schema.md`

## Assumptions and Defaults

- The control plane remains the orchestration source of truth and should describe multimodal payload identity explicitly enough for routing and metrics.
- Phase 6 multimodal execution stays in the Python worker plane.
- Existing text-message transport shapes remain valid, but multimodal parts gain typed metadata rather than relying on URI-vs-bytes inference alone.
- Speech synthesis is modeled in the shared worker protocol now even if the HTTP surface arrives later in Phase 6.
- Generated protocol artifacts stay committed in both the Swift and Python packages.

## Performance Probes

This milestone is contract-only, so runtime latency metrics remain `N/A`.

The contract work must still reserve stable probe names for later milestones:

- `vision.preprocess_latency_ms`
- `vision.ocr_latency_ms`
- `vision.vlm_first_token_ms`
- `audio.transcription_latency_ms`
- `audio.speech_latency_ms`
- `scheduler.multimodal_queue_delay_ms`

## Work Plan

### Task 1: Extend shared worker capability and media-input schema

**Objective**

Make OCR, VLM, transcription, and speech explicit in the worker protocol and add typed image/audio source metadata.

**Files**

- Modify: `packages/protocol/schema/worker/v1/common.proto`
- Modify: `packages/protocol/schema/worker/v1/inference.proto`
- Modify: `packages/protocol/schema/worker/v1/runtime.proto`
- Regenerate: `packages/protocol/swift/*`
- Regenerate: `packages/protocol/python/*`

**Implementation**

- Expand multimodal capability metadata to distinguish OCR, VLM, transcription, speech, and image-generation support.
- Introduce media-source and media-format metadata that can describe URI-backed and inline byte payloads consistently.
- Add speech request and response shapes beside transcription without changing the Phase 5 endpoint surface.
- Keep image-generation and edit shapes intact while isolating new Phase 6 media-analysis semantics.

**Verification**

- `make proto`
- `swift build --package-path packages/protocol/swift`

### Task 2: Extend control-plane protocol vocabulary for multimodal visibility

**Objective**

Expose enough control-plane vocabulary for multimodal route typing and future operator visibility.

**Files**

- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
- Regenerate: `packages/protocol/swift/*`
- Regenerate: `packages/protocol/python/*`

**Implementation**

- Add control-plane summary fields needed to distinguish OCR, VLM, transcription, and speech-capable models.
- Add media-normalization-facing enum or summary fields only where the control plane must surface them later.
- Avoid premature endpoint-specific control-plane commands in this slice.

**Verification**

- `make proto`

### Task 3: Add request-normalization fixtures and representational tests

**Objective**

Lock in accepted multimodal payload shapes before runtime logic lands.

**Files**

- Modify tests under `services/control-plane-swift/Tests/ControlPlaneTests`
- Modify tests under `services/control-plane-swift/Tests/HTTPGatewayTests`
- Modify tests under `services/mlx-worker-python/tests`

**Implementation**

- Add Swift-side request-normalization tests for image and audio parts in chat-style payloads.
- Add worker-side protobuf round-trip or service-contract tests for transcription and speech requests.
- Verify source kind, MIME type, and preprocessing-hint preservation across generated artifacts.

**Verification**

- `make swift-test`
- `make py-test`

### Task 4: Record milestone status and verification hooks

**Objective**

Leave a clean Phase 6 entry point for runtime work.

**Files**

- Modify: `docs/README.md`
- Modify or create: `docs/runbooks/*` only if a contract-specific note becomes necessary

**Implementation**

- Add the milestone plan to the docs index.
- Keep verification commands explicit so `P6-M2` can start from a stable contract baseline.

**Verification**

- `git diff --check`

## Acceptance

- Shared worker schemas can represent OCR, VLM, transcription, and speech-capable models without ambiguous overloads.
- Image and audio payloads carry typed normalization metadata beyond raw URI-vs-bytes selection.
- Generated Swift and Python protocol artifacts build cleanly after regeneration.
- Swift and Python tests cover accepted multimodal payload shapes and preserve contract fields.
- The touched repository scope remains at or above `95%` measured coverage before commit.

## Rollback and Safe Exit

- If speech output shapes prove premature, keep the capability metadata and reserve speech transport fields behind unused request types rather than shipping ad hoc placeholders later.
- If control-plane summaries are not yet stable, land worker-schema changes first and keep control-plane exposure limited to capability metadata already required for routing.
