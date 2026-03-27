# Phase 7 Image Generation, Image Editing, and Image Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add image generation and image editing as explicit long-running background workloads with isolated worker pools, artifact handling, progress reporting, cancellation semantics, and a native Image panel that do not destabilize text or analysis workloads.

**Architecture:** Melix keeps image generation and editing in dedicated Python worker classes and treats them as long-running background jobs rather than synchronous text-runtime variants. The control plane becomes responsible for job lifecycle visibility, cancellation, artifact metadata, and resource isolation while workers own actual image runtime execution. The native SwiftUI desktop app adds an Image panel only after those job and artifact surfaces are stable through the control plane.

**Tech Stack:** Swift 6, Swift Package Manager, Python 3.12, uv, gRPC over Unix Domain Sockets, local artifact storage, SwiftProtobuf and Python-generated protocol artifacts, XCTest, pytest, integration tests.

---

## Goal

Deliver a production-shaped Phase 7 implementation that exposes `POST /v1/images/generations` and `POST /v1/images/edits`, routes them to isolated image workers, reports progress and terminal state clearly, keeps text responsiveness intact under long-running image load, and adds a native Image panel with artifact workflows.

## Non-Goals

- Turn image generation into a synchronous text-style stream without job semantics.
- Move image workloads into the Swift text worker.
- Build a full gallery or creative UI in this phase.
- Introduce remote artifact storage or sharing services.
- Blur the distinction between fast multimodal analysis and heavy image generation jobs.
- Add training, adapter, or unrelated model-operations workflows that belong to other phases.

## Context

- Relevant specs:
  - `docs/architecture-spec.md`
  - `docs/worker-rpc-schema.md`
  - `docs/phase-roadmap.md`
  - `docs/plans/2026-03-27-phase-6-vision-ocr-audio-transcription.md`
- Relevant code paths:
  - `services/control-plane-swift/Sources/HTTPGateway`
  - `services/control-plane-swift/Sources/Requests`
  - `services/control-plane-swift/Sources/WorkerClient`
  - `services/control-plane-swift/Sources/EnginePool`
  - `services/mlx-worker-python/worker`
  - `tests/integration`
- Current constraints:
  - The current runtime model is optimized around request-response or stream-response paths, not long-running image jobs.
  - Artifact metadata and output handling are not yet first-class control-plane concerns.
  - Resource isolation must be stronger here than in prior phases because image work is expected to be the heaviest local background load.

## Assumptions

- Prior phases have already established dedicated background lanes and worker-class routing.
- Image generation and editing are implemented in Python worker classes first.
- Artifact payloads remain local-first and are surfaced via control-plane metadata plus local file references.
- Cancellation is mandatory and must be explicit for long-running jobs.
- The Image panel must remain a control-plane client and not bypass artifact or job metadata boundaries.

## Performance Probes and Metrics

Required probes:

- `images.job_latency_ms`
- `images.queue_wait_ms`
- `images.progress_update_interval_ms`
- `images.cancel_latency_ms`
- `images.peak_memory_bytes`
- `images.gpu_pressure_pct`
- `scheduler.text_ttft_under_image_load_ms`
- `desktop.image_action_latency_ms`
- `images.artifact_publish_ms`

Required comparison report:

- text-only baseline vs text-plus-image-job load
- generation vs editing latency on the same model class
- cancel success and cancel latency under active job execution
- job completion vs artifact visibility latency in the desktop app

## Work Plan

### Task 1: Finalize image-job protocol and artifact metadata contracts

**Objective**

Make image generation and editing explicit long-running job classes with clear progress, cancellation, and artifact references.

**Files**

- Modify: `packages/protocol/schema/worker/v1/common.proto`
- Modify: `packages/protocol/schema/worker/v1/inference.proto`
- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
- Regenerate: `packages/protocol/swift/**/*`
- Regenerate: `packages/protocol/python/**/*`

**Implementation**

- Add image job request and response metadata, progress state, terminal state, and artifact references.
- Keep artifact payloads out of the control plane while making output metadata operator-visible.
- Preserve cancellation and failure semantics in both worker and control-plane protocols.

**Verification**

- `make proto`

**Acceptance**

- The protocol can represent image jobs without pretending they are text streams.

### Task 2: Implement image generation and edit runtimes in dedicated Python worker classes

**Objective**

Add image-generation and image-edit execution paths with proper model lifecycle, runtime stats, and output handling.

**Files**

- Modify: `services/mlx-worker-python/worker/runtime/*`
- Modify: `services/mlx-worker-python/worker/engine/*`
- Modify: `services/mlx-worker-python/worker/model_registry/*`
- Modify tests under `services/mlx-worker-python/tests`

**Implementation**

- Add runtime adapters for image generation and image editing.
- Track job identity, progress, cancellation, and output artifact metadata.
- Keep image worker capability reporting distinct from text and analysis classes.

**Verification**

- `make py-test`

**Acceptance**

- The Python worker can execute image jobs, cancel them, and report outputs coherently.

### Task 3: Add control-plane endpoints, job state, and artifact reporting

**Objective**

Expose image work through stable local endpoints and make long-running job state visible to clients and operators.

**Files**

- Create or modify: `services/control-plane-swift/Sources/HTTPGateway/*`
- Modify: `services/control-plane-swift/Sources/Requests/*`
- Modify: `services/control-plane-swift/Sources/WorkerClient/*`
- Modify tests under `services/control-plane-swift/Tests/HTTPGatewayTests`

**Implementation**

- Add `POST /v1/images/generations` and `POST /v1/images/edits`.
- Surface job creation, progress, completion, cancellation, and failure metadata.
- Expose artifact references in a stable local form suitable for operator workflows and tests.

**Verification**

- `make swift-test`

**Acceptance**

- Clients can create image jobs and observe their lifecycle without reaching into worker internals.

### Task 4: Isolate image workloads from text and analysis traffic

**Objective**

Make heavy image jobs a controlled background class rather than an unbounded local resource grab.

**Files**

- Modify: `services/control-plane-swift/Sources/EnginePool/*`
- Modify: `services/control-plane-swift/Sources/Metrics/*`
- Modify related tests under `services/control-plane-swift/Tests`

**Implementation**

- Route image jobs to isolated workers or queues with clear admission and backpressure policy.
- Measure text TTFT and queue-delay interference under active image load.
- Define explicit operator-visible failure or rejection behavior when the system is saturated.

**Verification**

- `make swift-test`
- `make integration-test`

**Acceptance**

- Text responsiveness remains within the defined Phase 7 envelope under image-job load.

### Task 5: Add the native Image panel, integration evidence, runbooks, and metrics reporting

**Objective**

Leave Phase 7 with reproducible proof that image jobs, cancellation, artifact handling, and the native Image panel are stable.

**Files**

- Create or modify integration tests under `tests/integration`
- Create or modify: `docs/runbooks/*`
- Modify: `README.md`

**Implementation**

- Add integration cases for generation, editing, progress observation, cancellation, and output artifact metadata.
- Add the native Image panel for generation, edit, progress, and artifact preview workflows backed only by control-plane state.
- Document local operator workflow for loading image workers, observing job progress, and reproducing metrics.
- Standardize the Phase 7 metrics report for latency, resource pressure, cancel success, and artifact publish latency.

**Verification**

- `make swift-test`
- `make py-test`
- `make integration-test`
- `make coverage`

**Acceptance**

- Integration tests prove image-job lifecycle and cancellation behavior.
- The touched scope meets the `>=95%` coverage rule.
- The Phase 7 metrics report contains non-`N/A` image-job numbers.

## Verification

```bash
make proto
make swift-test
make py-test
make integration-test
make coverage
```

Expected evidence:

- image-job protocol generation succeeds
- Python worker tests cover generation, editing, and cancellation paths
- control-plane tests cover endpoint translation and artifact reporting
- integration covers long-running job progress, cancel, and output metadata
- touched-scope coverage is at least `95%`
- the metrics report includes latency, cancel, artifact publish, and interference numbers

## Acceptance Criteria

- Melix exposes `POST /v1/images/generations` and `POST /v1/images/edits`.
- Image jobs run in isolated background worker classes with explicit progress and cancellation.
- Output artifacts are surfaced through stable control-plane metadata.
- Text responsiveness remains protected under heavy image load.
- The native Image panel drives and observes image jobs without reaching into worker-private state.
- Phase 7 concludes with reproducible lifecycle, artifact, Image-panel, and metrics evidence.

## Rollback or Safe Exit

- Land protocol, worker execution, control-plane endpoints, and workload isolation as separate slices.
- Keep image jobs behind passing integration tests and explicit worker health checks until the full lifecycle is stable.
- If one image capability lags, ship generation and editing as separate milestones rather than forcing simultaneous completion.
