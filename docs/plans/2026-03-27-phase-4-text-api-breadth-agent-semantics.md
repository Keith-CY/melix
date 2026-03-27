# Phase 4 Text API Breadth and Desktop Ops Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand Melix from thin chat compatibility into a fuller local text-runtime surface with `completions`, `responses`, `messages`, richer reasoning and tool-call streams, workflow-aware request shaping, and the first real native desktop operations foundation built on the text runtime foundation from Phases 1 through 3.

**Architecture:** Melix keeps one text execution core and broadens the control-plane translation layer so multiple public text endpoint shapes map onto the same session, scheduler, cache, and worker model. Endpoint diversity lives in translation, stream semantics, and compatibility logic rather than in separate runtime backends. In parallel, the native SwiftUI desktop app grows a real dashboard, settings, logs, bench, models, and API reference foundation backed entirely by control-plane truth.

**Tech Stack:** Swift 6, Swift Package Manager, SwiftProtobuf-generated control-plane and worker contracts, local HTTP/SSE gateway, XCTest, Python integration harness for endpoint-level tests.

---

## Goal

Deliver a production-shaped Phase 4 implementation that adds `POST /v1/completions`, `POST /v1/responses`, and `POST /v1/messages`, normalizes reasoning and tool-call delta behavior across text APIs, makes workflow-aware request shaping a deliberate control-plane capability, and upgrades the native desktop shell from a thin operator view into a real desktop operations foundation.

## Non-Goals

- Add embedding, rerank, multimodal, or image endpoints.
- Rebuild the text runtime itself beyond the hooks needed for richer stream semantics.
- Introduce cross-provider compatibility hacks that violate Melix's internal request model.
- Ship chat, image, HuggingFace, quantization, or training workflows in the desktop app before their backend phases.
- Collapse endpoint-specific translation logic into worker-specific behavior.

## Context

- Relevant specs:
  - `docs/architecture-spec.md`
  - `docs/control-plane-protocol.md`
  - `docs/phase-roadmap.md`
  - `docs/plans/2026-03-27-phase-3-cache-session-recovery.md`
- Relevant code paths:
  - `services/control-plane-swift/Sources/HTTPGateway`
  - `services/control-plane-swift/Sources/HTTPGateway/OpenAI`
  - `services/control-plane-swift/Sources/HTTPGateway/SSE`
  - `services/control-plane-swift/Sources/Requests`
  - `services/control-plane-swift/Sources/Metrics`
  - `tests/integration`
- Current constraints:
  - Current public text surface is still centered on `/v1/chat/completions`.
  - Reasoning and tool deltas are not yet normalized across multiple endpoint families.
- Preset and workflow shaping remain implicit rather than first-class translation inputs.
  - The native desktop app still lacks Dashboard, Models, Tools, Settings, Logs, Bench, and API reference workflows backed by real control-plane state.

## Assumptions

- Phases 1 through 3 have stabilized the Swift text worker, phase-aware execution, and session or recovery behavior.
- Existing text endpoints remain backward compatible during the expansion.
- Workflow-aware shaping belongs in the control plane and not in worker-side request interpretation.
- Endpoint additions must reuse the same session, branch, and cache model rather than creating endpoint-specific state silos.

## Performance Probes and Metrics

Required probes:

- `http.translation_ms`
- `http.responses_translation_ms`
- `http.messages_translation_ms`
- `http.completions_translation_ms`
- `http.stream_first_event_ms`
- `http.reasoning_delta_count`
- `http.tool_delta_count`
- `http.stream_bytes`
- `http.endpoint_error_rate`
- `desktop.operator_action_latency_ms`
- `desktop.snapshot_hydration_ms`

Required comparison report:

- `/v1/chat/completions` vs `/v1/responses` vs `/v1/messages` translation overhead
- `/v1/chat/completions` vs `/v1/completions` vs `/v1/responses` vs `/v1/messages` translation overhead
- reasoning and tool delta fidelity across equivalent prompts
- endpoint-specific stream latency overhead against the existing chat baseline

## Work Plan

### Task 1: Extend the public API translation layer for completions, responses, and messages

**Objective**

Add the new text endpoint families while preserving one internal text execution model.

**Files**

- Create or modify: `services/control-plane-swift/Sources/HTTPGateway/*`
- Create or modify: `services/control-plane-swift/Sources/Requests/*`
- Modify tests under `services/control-plane-swift/Tests/HTTPGatewayTests`

**Implementation**

- Add `POST /v1/completions`, `POST /v1/responses`, and `POST /v1/messages` handlers.
- Normalize all text endpoints into the same internal request identity, session, and scheduling shape.
- Keep endpoint-specific compatibility logic in the translator layer only.

**Verification**

- `swift test --package-path services/control-plane-swift --filter HTTPGateway`

**Acceptance**

- The control plane can accept all three text endpoint families without changing the runtime route.

### Task 2: Define consistent reasoning and tool-call streaming semantics

**Objective**

Make streamed reasoning and tool output behavior explicit and stable across text endpoints.

**Files**

- Modify: `services/control-plane-swift/Sources/HTTPGateway/SSE/*`
- Modify: `services/control-plane-swift/Sources/Requests/*`
- Modify relevant protocol or event definitions only if needed for stream consistency
- Modify tests under `services/control-plane-swift/Tests/HTTPGatewayTests`

**Implementation**

- Standardize reasoning delta, tool-call delta, and terminal event sequencing.
- Ensure stream framing stays coherent whether the upstream request began as chat, responses, or messages.
- Keep worker output generic and let the control plane shape endpoint-specific stream envelopes.

**Verification**

- `make swift-test`

**Acceptance**

- Reasoning and tool deltas are stable and test-covered across supported text endpoints.

### Task 3: Add preset-aware and workflow-aware request shaping

**Objective**

Make request shaping an explicit control-plane responsibility so different client workflows can map cleanly onto one runtime.

**Files**

- Create or modify: `services/control-plane-swift/Sources/Requests/*`
- Create or modify: `services/control-plane-swift/Sources/ModelCatalog/*`
- Modify tests under `services/control-plane-swift/Tests/ControlPlaneTests`

**Implementation**

- Add explicit preset, workflow, and policy inputs to request translation.
- Define deterministic precedence between user-supplied request fields and control-plane defaults.
- Keep these shaping rules visible and testable rather than hidden in handler-specific branches.

**Verification**

- `swift test --package-path services/control-plane-swift --filter ControlPlane`

**Acceptance**

- Workflow-aware shaping is a real, reusable control-plane feature rather than duplicated per endpoint.

### Task 4: Preserve session, branch, and cache semantics across endpoint variants

**Objective**

Ensure the Phase 3 continuity model survives the broader API surface.

**Files**

- Modify: `services/control-plane-swift/Sources/Requests/*`
- Modify: `services/control-plane-swift/Sources/Snapshots/*`
- Modify integration tests under `tests/integration`

**Implementation**

- Keep session and branch state endpoint-agnostic.
- Verify that equivalent interactions through chat, responses, and messages reuse the same continuity model.
- Distinguish endpoint translation differences from runtime state ownership.

**Verification**

- `make integration-test`

**Acceptance**

- Session and branch continuity remain stable across the supported text endpoint families.

### Task 5: Add native desktop operations foundation and endpoint-level evidence

**Objective**

Leave Phase 4 with reproducible proof that the broader text API surface behaves consistently and that the native desktop shell now exposes real operator state.

**Files**

- Create or modify integration tests under `tests/integration`
- Modify: `README.md`
- Create or modify: `docs/runbooks/*`

**Implementation**

- Add endpoint-specific tests for `/v1/chat/completions`, `/v1/completions`, `/v1/responses`, and `/v1/messages`.
- Add coverage for reasoning deltas, tool deltas, and endpoint-specific error handling.
- Add Dashboard, Models, Settings, Logs, Bench, and API reference foundation in the native app only where backend support already exists.
- Record the metrics report format for translation latency, stream fidelity, and desktop action latency.

**Verification**

- `make swift-test`
- `make py-test`
- `make integration-test`
- `make coverage`

**Acceptance**

- Integration tests prove endpoint parity and stream correctness.
- The touched scope meets the `>=95%` coverage rule.
- The Phase 4 metrics report includes non-`N/A` endpoint comparison numbers.

## Verification

```bash
make swift-test
make py-test
make integration-test
make coverage
```

Expected evidence:

- new endpoint handlers pass unit tests
- stream semantics are stable under endpoint-specific integration tests
- session continuity remains correct across endpoint variants
- touched-scope coverage is at least `95%`
- the metrics report includes endpoint translation, stream-fidelity, and desktop action comparisons

## Acceptance Criteria

- Melix exposes `POST /v1/completions`, `POST /v1/responses`, and `POST /v1/messages` on top of the same text runtime.
- Reasoning and tool-call stream behavior is consistent across supported text endpoints.
- Workflow-aware request shaping is explicit, deterministic, and test-covered.
- Session, branch, and cache semantics remain endpoint-agnostic.
- The native desktop shell exposes real Dashboard, Models, Settings, Logs, Bench, and API reference workflows backed by control-plane truth.
- Phase 4 concludes with reproducible endpoint-level and desktop-foundation metrics evidence.

## Rollback or Safe Exit

- Land endpoint translation, stream normalization, and continuity-preservation slices independently so the existing chat path stays healthy.
- Keep `/v1/chat/completions` as the stable baseline until `/v1/responses` and `/v1/messages` each have their own passing integration coverage.
- If one endpoint family proves ambiguous or unstable, defer that family without weakening the already-stable text surface.
