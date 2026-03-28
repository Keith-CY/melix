# P5-M4 Model Operations Backend

**Date:** 2026-03-28  
**Phase:** Phase 5, Milestone 4  
**Status:** In Progress  
**Owner:** Codex

## Goal

Establish the first real Python worker backend for model-operations jobs so Melix can execute deterministic convert, quantize, download, and upload flows through `MaintenanceService`.

## Non-Goals

- No control-plane operator commands yet.
- No native desktop workflow yet.
- No real network transfer to HuggingFace in this milestone.
- No full background scheduler for long-running maintenance jobs.

## Context

Phase 5 already landed typed capability metadata, embedding runtime, and rerank runtime. The next backend slice is model operations. The existing worker maintenance protocol already provides `ConvertModel`, `GetModelInfo`, `RunDoctor`, and `RunBench`. This milestone uses `ConvertModel` plus typed ext fields to carry four deterministic job kinds:

- `convert`
- `quantize`
- `download`
- `upload`

That gives Phase 5 a stable backend substrate before the control plane and desktop shell expose the workflows.

## Performance Probes

The changed path must define and report:

- `model_ops.job_ms`
- `model_ops.job_kind`
- `model_ops.manifest_bytes`
- `model_ops.artifact_bytes`

## Work Plan

### Task 1: Add model-operations job state

Introduce internal job records so maintenance flows can create job identifiers, track stage transitions, store manifest payloads, and capture terminal output paths.

### Task 2: Activate `MaintenanceService`

Register `MaintenanceService` in the Python worker server and implement:

- `ConvertModel`
- `GetModelInfo`

Keep `RunDoctor` and `RunBench` structured but minimal.

### Task 3: Support deterministic convert, quantize, download, and upload jobs

Use `ConvertModelRequest.ext["operation"]` to select the job kind. Each run should:

- emit `started`, `progress`, and `completed`
- optionally emit `manifest`
- write deterministic placeholder artifacts into the requested output directory

### Task 4: Verify job behavior and capture metrics

Add tests for:

- service registration
- convert and quantize manifest flows
- download and upload job output handling
- model info lookup for known dev models

Capture a deterministic job-duration report.

## Verification

Run at least:

```bash
make py-test
git diff --check
```

If the touched Python scope remains measurable, run coverage for the worker package and report the result.

## Acceptance Criteria

- `MaintenanceService` is registered on the worker gRPC server.
- `ConvertModel` supports deterministic `convert`, `quantize`, `download`, and `upload` flows.
- `GetModelInfo` returns structured metadata for known dev models.
- Job identifiers, stage progress, manifest payloads, and output paths are reproducible.
- The metrics report includes non-`N/A` deterministic job timing data.

## Safe Exit

If job orchestration proves unstable, revert `MaintenanceService` to structured `unimplemented` responses without disturbing text, embedding, or rerank paths.
