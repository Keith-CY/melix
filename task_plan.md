# Task Plan

## Goal

Close `M16.1` by defining a first-class video ingress contract that normalizes supported video
inputs, validates preprocessing bounds, and exposes inspectable metadata without yet introducing
frame extraction or video-runtime execution.

## Scope

- extend the worker protocol with explicit video message-part and metadata fields
- add Swift-side multimodal decoding and normalization support for `input_video`
- add worker-side contract validation helpers for normalized video parts
- add focused Swift and Python coverage that proves accepted source forms and structured failures

## Measurement Points

- supported source forms normalize through one path: local path, file URI, remote URL, and inline
  base64 video bytes
- normalized metadata preserves `media_type`, `source_kind`, `mime_type`, `format`, `filename`,
  `duration_ms`, `frame_budget`, and time-bound hints
- unsupported containers, missing payloads, invalid base64, and invalid preprocessing bounds fail
  with structured errors
- changed-line coverage for the touched executable scope remains at or above `95%`

## Phases

1. Current-state review and contract design
   - status: completed
   - evidence:
     - reviewed `M16`, `M16.1`, the worker `MessagePart` and `MediaMetadata` schemas, existing
       image and audio normalization in `MultimodalRequestNormalizer`, and current Python
       multimodal preprocessing helpers
     - selected an analysis-first contract slice: protocol plus validation only, with no frame
       extraction or scheduler-routing changes until `M16.2`
2. Protocol and generated artifact expansion
   - status: completed
   - evidence:
     - extended `packages/protocol/schema/worker/v1/common.proto` with `MEDIA_TYPE_VIDEO`,
       `video_uri`, `video_bytes`, and explicit `frame_budget`, `start_ms`, and `end_ms`
     - regenerated `packages/protocol/python/worker/v1/common_pb2.py`,
       `packages/protocol/swift/worker/v1/common.pb.swift`, and
       `packages/protocol/descriptors/melix.pb` through `make proto`
3. Swift multimodal normalization and contract tests
   - status: completed
   - evidence:
     - added `OpenAIMultimodalVideoReference` plus `input_video` decoding, top-level convenience
       fields, format inference, URI validation, and preprocessing-bound validation in
       `MultimodalRequestNormalizer`
     - added focused `MultimodalContractTests` coverage for URI, inline-base64, filename and URL
       inference, typed operator errors, missing payloads, and scalar bound failures
     - added one `RequestCoordinatorTests` black-box assertion proving `video` message parts remain
       dispatchable during the ingress-only slice without forcing `M16.2` scheduling changes
4. Python video-ingress validation and coverage bookkeeping
   - status: completed
   - evidence:
     - added `worker/runtime/video_preprocessing.py` as the worker-side contract validator for
       normalized video parts, with structured URI, format, filename, and preprocessing-bound
       checks
     - added focused protobuf round-trip coverage in `test_multimodal_contracts.py` and dedicated
       validation coverage in `test_video_preprocessing.py`
     - verified touched-scope executable coverage at or above `95%` for both Swift and Python

## Acceptance

- Melix has one explicit normalized video-input contract before runtime execution work begins
- video metadata and preprocessing bounds are inspectable through the shared request model
- invalid ingress shapes fail predictably and test coverage keeps changed-line coverage above `95%`

## Risks

- if video reuses image-only fields, later frame-selection and cleanup work will inherit ambiguous
  semantics
- if URI, inline bytes, and preprocessing bounds are not normalized together, `M16.2` will need to
  rediscover transport-specific assumptions in runtime code
- if the first slice reaches into frame extraction early, it will blur the boundary between ingress
  contracts and runtime scheduling work
