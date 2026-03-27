# Phase 5 Embeddings, Rerank, and Model Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add dedicated embedding and rerank capability families plus the first real model-operations workflows on top of the stabilized text runtime without regressing interactive text responsiveness.

**Architecture:** Melix keeps the Swift text worker as the latency-critical text engine and extends the Python worker plane for the first dedicated non-generative model classes and model-operations jobs. The control plane becomes responsible for capability-class routing, mixed-workload isolation, operator-visible model metadata, per-model settings, and HuggingFace or quantization workflow orchestration while Python workers own embedding, rerank, conversion, quantization, upload, and download behavior.

**Tech Stack:** Swift 6, Swift Package Manager, Python 3.12, uv, gRPC over Unix Domain Sockets, SwiftProtobuf-generated and Python-generated protocol artifacts, XCTest, pytest, integration tests under `tests/integration`.

---

## Goal

Deliver a production-shaped Phase 5 implementation that exposes `POST /v1/embeddings` and `POST /v1/rerank`, routes them to dedicated Python worker classes, introduces per-model settings plus conversion and quantization plus HuggingFace workflows, and proves that mixed workloads do not erode the default text experience.

## Non-Goals

- Move embedding or rerank workloads into the Swift text worker.
- Introduce multimodal analysis or image generation in this phase.
- Add image, chat, or training workflows that belong to later phases.
- Overload the text scheduler with background workload semantics that should belong to dedicated worker classes.
- Treat rerank as a disguised chat task.

## Context

- Relevant specs:
  - `docs/architecture-spec.md`
  - `docs/worker-rpc-schema.md`
  - `docs/phase-roadmap.md`
  - `docs/plans/2026-03-27-phase-4-text-api-breadth-agent-semantics.md`
- Relevant code paths:
  - `services/control-plane-swift/Sources/HTTPGateway`
  - `services/control-plane-swift/Sources/WorkerClient`
  - `services/control-plane-swift/Sources/ModelCatalog`
  - `services/control-plane-swift/Sources/EnginePool`
  - `services/mlx-worker-python/worker`
  - `services/mlx-worker-python/tests`
  - `packages/protocol/schema/worker/v1/*.proto`
  - `tests/integration`
- Current constraints:
  - Current non-text worker support is still narrow and text-centric.
- The model catalog is not yet typed strongly enough for embedding and rerank routing.
- Mixed-workload interference has not yet been measured or controlled.
  - Per-model settings, quantization jobs, and HuggingFace artifact workflows are not yet represented as first-class control-plane commands.

## Assumptions

- The Swift text path remains the default latency-sensitive route.
- Embeddings and rerank are implemented in Python workers first because they fit the broader worker plane without requiring the Swift text hot path.
- The external API shape follows the canonical roadmap endpoints without inventing new families.
- Background or retrieval-class workloads should not occupy the same scheduling lane as interactive text decode.
- This phase is the right place to add advanced model-operations workflows before training arrives in Phase 8.

## Performance Probes and Metrics

Required probes:

- `embeddings.request_latency_ms`
- `embeddings.items_per_second`
- `rerank.request_latency_ms`
- `rerank.documents_per_second`
- `scheduler.mixed_workload_text_ttft_ms`
- `scheduler.mixed_workload_queue_delay_ms`
- `worker.memory_bytes_by_class`
- `worker.load_model_ms_by_class`
- `model_ops.quantize_job_ms`
- `model_ops.upload_job_ms`
- `model_ops.download_job_ms`
- `model_ops.transfer_bytes_per_second`

Required comparison report:

- text-only baseline vs text-plus-embeddings load
- text-only baseline vs text-plus-rerank load
- embedding throughput and rerank latency for the default development models
- quantized vs unquantized artifact footprint
- upload and download throughput for representative HuggingFace artifacts

## Work Plan

### Task 1: Finalize capability-class protocol, model-catalog support, and per-model settings

**Objective**

Make model capability typing, per-model settings, and request routing explicit enough to support text, embedding, rerank, and model-operations jobs simultaneously.

**Files**

- Modify: `packages/protocol/schema/worker/v1/common.proto`
- Modify: `packages/protocol/schema/worker/v1/runtime.proto`
- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
- Regenerate: `packages/protocol/swift/**/*`
- Regenerate: `packages/protocol/python/**/*`

**Implementation**

- Add or complete capability-class metadata for embedding and rerank models.
- Extend runtime stats and model catalog metadata to distinguish worker families clearly.
- Add model alias, type override, TTL, pinning, memory policy, and acceleration-profile metadata.
- Keep the control plane as the routing source of truth.

**Verification**

- `make proto`
- `swift build --package-path packages/protocol/swift`

**Acceptance**

- The control plane can classify models and worker routes without out-of-band naming hacks.

### Task 2: Implement embedding, rerank, and model-operations runtimes in the Python worker

**Objective**

Add real embedding and rerank execution paths plus quantization, upload, and download jobs in the Python worker without weakening the existing text-compatible worker behavior it still owns.

**Files**

- Modify: `services/mlx-worker-python/worker/runtime/*`
- Modify: `services/mlx-worker-python/worker/engine/*`
- Modify: `services/mlx-worker-python/worker/model_registry/*`
- Modify tests under `services/mlx-worker-python/tests`

**Implementation**

- Add runtime adapters and request handling for embedding and rerank models.
- Add advanced quantization workflows, artifact uploader and downloader flows, and manifest handling as model-operations jobs.
- Keep model lifecycle, capability reporting, and request metrics separate by workload class.
- Return explicit structured failures for unsupported model or request combinations.

**Verification**

- `make py-test`

**Acceptance**

- The Python worker can load, execute, and report embedding and rerank requests coherently.

### Task 3: Add control-plane endpoint translation, route selection, and model-operations commands

**Objective**

Expose embeddings and rerank through the local API surface while preserving route isolation from the interactive text path, and add control-plane-visible workflows for model operations and operator endpoints.

**Files**

- Create or modify: `services/control-plane-swift/Sources/HTTPGateway/*`
- Modify: `services/control-plane-swift/Sources/WorkerClient/*`
- Modify: `services/control-plane-swift/Sources/ModelCatalog/*`
- Modify tests under `services/control-plane-swift/Tests/HTTPGatewayTests`

**Implementation**

- Add `POST /v1/embeddings` and `POST /v1/rerank`.
- Route requests by capability class and worker type rather than by endpoint name alone.
- Preserve consistent error handling and model visibility through `/v1/models`.
- Add control-plane command and desktop-facing workflow support for model settings, quantization, download, and upload.
- Add `/v1/cache/stats`, `/health`, and Ollama-compatible endpoint support where those surfaces can be backed by the already-stabilized cache and model-routing state.

**Verification**

- `make swift-test`

**Acceptance**

- The control plane can expose both endpoints without treating them as text-runtime variants.

### Task 4: Protect text responsiveness under mixed workload

**Objective**

Make mixed text plus retrieval-class traffic measurable and controlled rather than hoping background jobs remain cheap.

**Files**

- Modify: `services/control-plane-swift/Sources/EnginePool/*`
- Modify: `services/control-plane-swift/Sources/Metrics/*`
- Modify related tests under `services/control-plane-swift/Tests`

**Implementation**

- Assign embedding and rerank work to non-interactive lanes or worker pools.
- Record interference metrics against text TTFT and queue delay.
- Add explicit admission or backpressure behavior when retrieval-class workers are saturated.

**Verification**

- `make swift-test`
- `make integration-test`

**Acceptance**

- Text latency remains within the defined Phase 5 acceptance envelope under mixed traffic.

### Task 5: Add integration coverage, native model-ops workflows, and metrics reporting

**Objective**

Leave Phase 5 with reproducible evidence for endpoint behavior, worker routing, mixed-load isolation, and model-operations workflows.

**Files**

- Create or modify integration tests under `tests/integration`
- Modify: `README.md`
- Create or modify: `docs/runbooks/*`

**Implementation**

- Add integration tests for `/v1/embeddings`, `/v1/rerank`, model settings, quantization jobs, and HuggingFace upload or download workflows.
- Document local operator workflow for loading models, observing worker classes, configuring per-model settings, and reproducing the metrics report.
- Add native desktop `Models` and `Tools` workflows only where backend support already exists.
- Record throughput, interference, and model-operations metrics in a standard Phase 5 report shape.

**Verification**

- `make swift-test`
- `make py-test`
- `make integration-test`
- `make coverage`

**Acceptance**

- Integration tests explicitly prove endpoint behavior and text-isolation guarantees.
- The touched scope meets the `>=95%` coverage rule.
- The Phase 5 metrics report contains non-`N/A` throughput and mixed-load data.

## Verification

```bash
make proto
make swift-test
make py-test
make integration-test
make coverage
```

Expected evidence:

- capability-class protocol generation succeeds
- Python worker tests cover embedding and rerank paths
- control-plane tests cover routing and endpoint translation
- integration covers embeddings, rerank, and mixed-load isolation
- touched-scope coverage is at least `95%`
- the metrics report includes throughput, latency, text-interference, and model-operations numbers

## Acceptance Criteria

- Melix exposes `POST /v1/embeddings` and `POST /v1/rerank`.
- The control plane routes those requests to dedicated Python worker classes rather than the Swift text engine.
- Mixed text and retrieval-class traffic remains observable and controlled.
- Model visibility and health state reflect multiple capability classes cleanly.
- Per-model settings, advanced quantization, and HuggingFace artifact workflows are reproducible and operator-visible.
- Phase 5 concludes with reproducible endpoint, routing, model-operations, and metrics evidence.

## Rollback or Safe Exit

- Land capability typing, Python worker execution, control-plane endpoints, and mixed-load controls in separate slices.
- Keep the text path isolated from incomplete retrieval-class work throughout the phase.
- If rerank or embedding support proves unstable, ship whichever class meets correctness and interference gates first without blocking the other.
