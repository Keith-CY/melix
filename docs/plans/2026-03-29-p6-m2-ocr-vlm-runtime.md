# P6-M2 OCR and VLM Runtime

**Date:** 2026-03-29  
**Phase:** Phase 6, Milestone 2  
**Status:** In Progress  
**Owner:** Codex

## Goal

Activate worker-local OCR and VLM execution in the Python worker plane with explicit image preprocessing, deterministic smoke coverage, and measurable preprocessing probes.

## Non-Goals

- No control-plane multimodal endpoint work yet.
- No native Chat panel work yet.
- No audio transcription or speech runtime in this milestone.
- No live non-deterministic VLM dependency requirement for local verification.

## Context

`P6-M1` landed the multimodal protocol shapes and control-plane normalization contracts. `P6-M2` should keep the public API unchanged and make the Python worker capable of:

- loading OCR and VLM-class dev models
- preprocessing inline image bytes and local file URIs
- executing deterministic OCR extraction and image-to-text VLM generation
- reporting worker capabilities and maintenance metadata that reflect the new model classes

This slice should avoid speculative endpoint work and stay inside the worker runtime, registry, and tests.

## Performance Probes

The changed path must define and report:

- `vision.preprocess_latency_ms`
- `vision.preprocess_input_bytes`
- `vision.preprocess_peak_memory_bytes`
- `vision.ocr_latency_ms`
- `vision.vlm_first_token_ms`

The first metrics report may use deterministic runtimes as long as the numbers are non-`N/A` and reproducible.

## Work Plan

### Task 1: Add multimodal preprocessing primitives

Introduce a worker-local preprocessing layer that can normalize image inputs from:

- inline bytes
- local file URIs

The preprocessing layer should preserve source identity, media metadata, byte counts, and deterministic failure modes.

### Task 2: Add deterministic OCR and VLM runtimes

Introduce dedicated OCR and VLM runtimes for Python workers. Each runtime should expose:

- model load
- resident-byte estimate
- prompt rendering from multimodal messages
- deterministic token generation
- probe snapshots for preprocessing and execution timing

### Task 3: Teach the worker registry and catalog about OCR and VLM models

Extend the worker model catalog and registry so they can:

- resolve `melix-dev-ocr`
- resolve `melix-dev-vlm`
- load and track OCR and VLM handles distinctly from text, embeddings, and rerank
- report multimodal capability flags coherently

### Task 4: Verify deterministic worker smoke and maintenance metadata

Add tests for:

- loading OCR and VLM dev models
- OCR extraction from inline image bytes
- image-to-text VLM generation from a file URI
- capability reporting and maintenance metadata for the new model classes

## Verification

Run at least:

```bash
make py-test
git diff --check
```

If the touched Python scope remains measurable, run coverage for the worker package and report the result.

## Acceptance Criteria

- `WorkerModelCatalog` exposes OCR and VLM dev models.
- `RuntimeService.LoadModel` can load both models.
- The worker can preprocess inline image bytes and local file URIs deterministically.
- OCR smoke returns extracted text from an image input.
- VLM smoke returns an image-conditioned text response from an image input.
- The metrics report includes non-`N/A` deterministic preprocessing and execution timings.

## Safe Exit

If the runtime slice becomes unstable, keep the capability typing and catalog additions but revert the execution path to structured `unimplemented` without touching the already landed control-plane multimodal contracts.
