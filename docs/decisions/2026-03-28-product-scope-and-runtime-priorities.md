# Product Scope and Runtime Priorities

Date: 2026-03-28

## Summary

Melix should widen its roadmap in two directions at once:

- it should deepen the text runtime with acceleration and durable reuse before broadening into all product surfaces
- it should also plan the full local product surface early enough that desktop operations, model workflows, and backend capabilities evolve together rather than as disconnected tracks

This decision records the product and architecture priorities that now guide the roadmap beyond Phase 1.

## Decisions

### Native Desktop Product

The long-term local product surface is a native SwiftUI desktop app backed only by the control plane.

The desktop app should eventually expose:

- dashboard
- models
- tools
- settings
- logs
- bench
- chat
- image
- HuggingFace workflows
- training workflows

These surfaces must not ship as placeholder views disconnected from backend truth.

### Unified Cache Strategy

Melix adopts a merged cache architecture rather than a single cache pattern.

The cache stack should combine:

- hot in-memory prefix or paged reuse
- disk-backed block or snapshot persistence
- block-table metadata
- cache quantization at the storage boundary
- restart-safe restore and snapshot flows

The control plane owns cache metadata truth. Workers own cache payloads and active runtime state.

### Runtime Acceleration Priority

Advanced text acceleration is a roadmap priority before broad UI polish.

The early runtime roadmap should explicitly include:

- draft-model speculative decoding
- accelerated prefill or prompt-lookup style reuse for repetitive prompts
- active-path low-bit KV cache modes where safe

These capabilities belong to the text-runtime phases rather than being deferred to final productization.

### Model Operations as Product Features

Model operations are first-class product capabilities, not hidden maintenance scripts.

The roadmap should include:

- per-model settings
- conversion and quantization workflows
- HuggingFace download and upload
- benchmark and diagnostics workflows

These workflows should land through control-plane commands and worker jobs first, then be surfaced through the native desktop app.

### Training Scope

Training scope is limited to LoRA and QLoRA.

This includes:

- local job execution
- adapter packaging
- adapter registry or catalog behavior
- upload and distribution workflows

This does not include full-parameter fine-tuning.

### Backend Capability Assumptions

Some performance-critical capabilities belong to the MLX runtime layer rather than to control-plane modules.

Melix should treat the following as backend assumptions to benchmark and validate, not as first-class orchestration services:

- quantized matrix multiplication
- SDPA and related attention kernels

By contrast, image generation remains a distinct worker-family capability and product workflow.

## Consequences

- Phase 2 must grow from pure phase-aware text execution into phase-aware plus acceleration-aware execution.
- Phase 3 must make the cache stack explicitly tiered and quantization-aware.
- Phase 4 through Phase 8 must bring desktop operations, model operations, and full API breadth into the roadmap earlier than before.
- Formal Melix docs should describe these capabilities in Melix-native language rather than using external feature branding.
