# Melix Phase Roadmap

Date: 2026-04-12

## How To Read This Document Now

This document started as the original phase-by-phase execution sequence for Melix. It now serves
as a closure summary for that early roadmap rather than as the best day-to-day project status
entrypoint.

Use these documents together:

- [`current-status.md`](current-status.md) for the current product-facing summary
- [`plans/2026-03-30-full-capability-roadmap-execution-index.md`](plans/2026-03-30-full-capability-roadmap-execution-index.md) for milestone-level closure detail
- [`../progress.md`](../progress.md) for the latest repository progress notes and known local issues

## Current Completion Summary

For the active repository slice, the original Phase `0-8` roadmap is complete:

- Phase 0 established the thin-path baseline.
- Phase 1 moved the text hot path into the Swift text worker.
- Phases 2-7 expanded runtime depth, API breadth, multimodal support, model operations, benchmark and evaluation tooling, and operator surfaces.
- Phase 8 closed the current local-product slice around LoRA workflows, packaging, release gates, and acceptance evidence.

After the original phase model, repository work continued under the detailed milestone families in
the full capability execution index. That milestone archive is now the authoritative detailed
record.

## What The Repository Ships At The End Of The Phase 8 Product Slice

- typed local control-plane and worker protocols
- Swift control-plane and text-worker product paths
- Python worker execution and productization workflows
- CLI-first local model operations, server-session control, chat, LoRA, benchmark, and evaluation
- native macOS operator workflows backed by the same product authority
- local install, packaging, release-gate, and acceptance evidence paths

## Honest Current Boundary

- Apple Silicon and macOS remain the intended product boundary.
- Disk-streaming still has evidence and operator documentation, but not true shipped SSD-backed runtime execution.
- Historical plans describe more exploration than the current curated product docs. Treat archived plans as engineering history unless a current status or runbook document says otherwise.

## Historical Phase Sequence

### Phase 0: Thin Path Baseline

Status:

- complete

Delivered outcome:

- one executable local path from HTTP request to streamed worker output
- typed control-plane and worker protocols
- deterministic integration fixtures and real MLX streaming path
- minimal menu bar operator shell

### Phase 1: Swift Text Worker Hot Path

Status:

- complete

Delivered outcome:

- the default text path moved to a dedicated Swift text worker
- text streaming and abort support route through the Swift worker path
- Python remained the execution layer for non-text families

### Phase 2: Text Runtime Depth And Acceleration

Status:

- complete

Delivered outcome:

- phase-aware request flow, queueing visibility, scheduler behavior, and acceleration-aware text execution
- observable prefill or decode behavior and richer request lifecycle reporting

### Phase 3: Unified Cache, Session Graph, And Recovery

Status:

- complete

Delivered outcome:

- cache-aware runtime and recovery planning work became first-class repository scope
- reusable session and recovery behavior landed in the control-plane and productization layers

### Phase 4: Text API Breadth And Desktop Ops Foundation

Status:

- complete

Delivered outcome:

- broader compatibility surfaces and workflow-aware request shaping
- the native desktop ops foundation moved from placeholder shell to real operator state

### Phase 5: Embeddings, Rerank, And Model Operations

Status:

- complete

Delivered outcome:

- first-class embedding, rerank, and model-operations surfaces
- typed registry and model-family expansion work

### Phase 6: Vision, OCR, Audio, And Chat Panel

Status:

- complete

Delivered outcome:

- multimodal analysis, OCR, speech-related runtime coverage, and chat-surface integration

### Phase 7: Image Generation, Image Editing, And Image Panel

Status:

- complete

Delivered outcome:

- image-generation and edit workflows plus native image-surface integration

### Phase 8: Training, Desktop Productization, Packaging, And Release Hardening

Status:

- complete

Delivered outcome:

- LoRA and QLoRA workflows through product-owned surfaces
- packaging, install, release-gate, and acceptance-evidence closure for the active local product slice

## Delivery Rules That Still Apply

- Keep `packages/protocol/schema` as the editable interface source of truth.
- Do not claim a feature is shipped unless the current status docs and verification evidence agree.
- End each substantial behavior change with updated documentation and an honest metrics note for the touched scope.
