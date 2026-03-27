# Melix Phase Roadmap

Date: 2026-03-27

## Summary

Melix has completed Phase 0 and now has a stable thin-path baseline:

- generated protocol artifacts
- a Swift control plane
- a Python worker
- streamed local chat over HTTP/SSE
- live worker transport over local RPC
- real MLX token streaming in worker `auto` mode
- a minimal operator-facing menu bar shell
- a reproducible local operator workflow

This roadmap defines the recommended order for the next phases. The sequence is intentionally runtime-first, but it now starts by moving the default text hot path into a dedicated Swift text worker before deeper phase-aware scheduling and cache work.

## Roadmap Principles

- Strengthen runtime depth before expanding endpoint breadth.
- Improve the latency-critical text path without collapsing the control-plane/worker boundary.
- Add new public surfaces only after the underlying routing and execution model are ready.
- Keep deterministic execution as the default integration path until each capability family has a stable live smoke path.
- Treat each phase as complete only when tests, operator workflow, and metrics evidence are in place.

## Phase Sequence

### Phase 0: Thin Path Baseline

Status:

- complete

Delivered outcome:

- one executable local path from HTTP request to streamed worker output
- typed control-plane and worker protocols
- deterministic integration path and real MLX streaming path
- minimal menu bar operator shell

### Phase 1: Swift Text Worker Hot Path

Primary objective:

- move the default text `Generate` path into an independent Swift text worker

Major additions:

- a dedicated Swift text worker behind the shared worker RPC contract
- default text model routing to the Swift worker
- Swift-side text streaming, abort, and lifecycle support
- explicit failure behavior on Swift text worker errors rather than silent Python fallback

Exit criteria:

- `POST /v1/chat/completions` uses the Swift text worker by default
- text streaming and abort are stable through the Swift worker path
- Python remains the execution layer for non-text families
- the control plane can route by worker engine class without changing the public API shape

Phase probes:

- TTFT
- tokens per second
- abort latency
- model load latency
- peak memory for the default text model

### Phase 2: Text Runtime Depth

Primary objective:

- deepen the Swift text path from end-to-end `Generate` into phase-aware text execution

Major additions:

- real `Prefill` and `Decode` worker paths
- lane-aware scheduler behavior for interactive decode and prefill classes
- richer request progress and admission state in the control plane
- correct abort handling across queued, prefill, and decode states

Exit criteria:

- follow-up requests can use explicit prefill/decode flow
- scheduler decisions reflect lane and priority hints rather than simple FIFO behavior
- queueing and abort behavior are observable and test-covered

Phase probes:

- admission latency
- queue delay p50 and p95
- TTFT
- tokens per second
- abort latency

### Phase 3: Cache, Session Graph, and Recovery

Primary objective:

- make reuse and resume first-class instead of opportunistic

Major additions:

- L1 block reuse and observable block-table metadata
- checkpoint and snapshot save or restore flows
- session graph state with branch lineage and resume references
- cache-aware scheduling and prefix affinity

Exit criteria:

- same-session follow-ups show measurable TTFT improvement
- tool-boundary recovery can resume from saved state
- cache metadata and recovery state are visible through the control plane

Phase probes:

- cache hit rate
- block reuse ratio
- snapshot restore latency
- follow-up TTFT delta vs cold run
- cache memory and SSD footprint

### Phase 4: Text API Breadth and Agent Semantics

Primary objective:

- expand from thin chat compatibility to a fuller text-runtime API surface

Major additions:

- `POST /v1/responses`
- `POST /v1/messages`
- richer reasoning and tool-call stream semantics
- preset-aware and workflow-aware request shaping

Exit criteria:

- chat-completions, responses, and messages flows behave consistently over the same runtime model
- tool and reasoning streams are stable and test-covered
- session and branch metadata survive across endpoint variants

Phase probes:

- translation latency by endpoint
- stream event latency
- reasoning and tool delta fidelity
- endpoint overhead vs chat-completions baseline

### Phase 5: Embeddings and Rerank

Primary objective:

- add the first dedicated non-generative worker classes without regressing text responsiveness

Major additions:

- `POST /v1/embeddings`
- `POST /v1/rerank`
- embed-capable and rerank-capable worker routing
- model catalog typing for capability-class dispatch

Exit criteria:

- embedding and rerank workloads route to dedicated workers
- text latency remains stable under mixed traffic
- model visibility and health state reflect multiple worker classes

Phase probes:

- embeddings throughput
- rerank latency
- mixed-workload interference on text TTFT
- memory pressure by model class

### Phase 6: Vision, OCR, and Audio Transcription

Primary objective:

- add analysis-style multimodal capabilities before generative image work

Major additions:

- VLM and OCR execution paths
- `POST /v1/audio/transcriptions`
- multimodal preprocessing for image and audio inputs
- background-lane routing for multimodal analysis tasks

Exit criteria:

- OCR and transcription are exposed through stable local APIs
- multimodal analysis workloads do not block interactive text decode
- worker and model metadata clearly surface multimodal capability

Phase probes:

- transcription latency
- OCR latency
- VLM first-token latency
- multimodal preprocessing memory spikes

### Phase 7: Image Generation and Image Editing

Primary objective:

- add the heaviest background generative workloads after queueing and worker isolation are already mature

Major additions:

- `POST /v1/images/generations`
- `POST /v1/images/edits`
- isolated image worker pools
- long-running job progress and cancellation semantics

Exit criteria:

- image jobs run without collapsing text responsiveness
- cancellation and failure states are explicit and operator-visible
- output artifacts and job metadata are surfaced consistently

Phase probes:

- image job latency
- queue wait under mixed traffic
- peak memory and GPU pressure
- cancellation success rate

### Phase 8: Desktop Productization, Packaging, and Release Hardening

Primary objective:

- turn Melix from an engineering runtime into a shippable local product

Major additions:

- richer dashboard, settings, logs, presets, and diagnostics flows
- cache inspector and operator tooling where prior phases already provide the backend support
- launchd, packaging, signing, installer/runtime bootstrap, and release runbooks
- benchmark and smoke gating for release candidates

Exit criteria:

- fresh install to ready-state is reproducible
- daemon and worker restart flows are recoverable
- release candidates carry benchmark and smoke evidence instead of only functional test evidence

Phase probes:

- cold boot to ready
- crash recovery success rate
- operator action latency
- benchmark regression thresholds
- packaging and install success rate

## Delivery Rules Across Phases

- Do not introduce new public endpoints in a phase whose runtime routing is still placeholder logic.
- Do not build rich UI flows for capabilities that are still thin-path placeholders.
- Keep `packages/protocol/schema` as the editable interface source of truth in every phase.
- End every phase with an updated phase-status document and a metrics report for the changed paths.

## Assumptions and Defaults

- This roadmap starts from the repository truth where Phase 0 is complete.
- The roadmap is an engineering execution sequence, not a marketing timeline.
- The optional admin web surface remains secondary to the native macOS shell unless a later task promotes it.
- Packaging and release work intentionally come after runtime and API stabilization.
- The default text engine direction is now an independent Swift text worker rather than a Python-only text path.
