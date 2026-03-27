# Melix Architecture Spec

Date: 2026-03-27

## Summary

Melix is a native control plane plus worker-runtime architecture for local AI execution on Apple Silicon. The system is built around four layers:

1. A macOS menu bar app and dashboard for local operations.
2. A Swift control plane daemon that owns system truth.
3. A polyglot worker pool connected over local RPC.
4. A tiered cache and storage layer that persists reusable execution state.

The design is optimized for agent-oriented workloads: repeated prefixes, tool-call recovery, branch-aware sessions, and fast follow-up requests.

Melix should keep the control plane Swift-first while moving the latency-critical default text path toward a dedicated Swift text worker. Python workers remain the primary execution layer for multimodal, embeddings, rerank, image, audio, and maintenance flows. See `decisions/2026-03-27-swift-text-runtime.md`.

## Runtime Topology

```text
┌────────────────────────────────────────────────────────────┐
│                Melix Menu Bar App (SwiftUI)               │
│  status, models, cache, presets, logs, bench, settings    │
└────────────────────────────────────────────────────────────┘
                            │ XPC
                            ▼
┌────────────────────────────────────────────────────────────┐
│             Melix Control Plane Daemon (Swift)            │
│  HTTP/SSE gateway, scheduler, EnginePool, CacheIndex,     │
│  SessionRegistry, WorkerRegistry, metrics, admin          │
└────────────────────────────────────────────────────────────┘
                 │ gRPC over Unix Domain Sockets
                 ▼
┌────────────────────────────────────────────────────────────┐
│              Melix Worker Pool (Swift + Python)           │
│  swift text, python multimodal, maintenance, embeddings   │
└────────────────────────────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────────┐
│                 Cache and Storage Layer                    │
│  L0 active state, L1 memory blocks, L2 SSD blocks,        │
│  boundary snapshots, metadata index                       │
└────────────────────────────────────────────────────────────┘
```

## Naming and Runtime Identifiers

Melix should use a single naming system across product docs and implementation examples.

- Repository root: `melix/`
- App bundle identifier: `com.melix.app`
- Control plane identifier: `com.melix.controlplane`
- XPC service identifier: `com.melix.controlplane.xpc`
- CLI name: `melix`
- Socket root: `/var/run/melix/`

Example socket layout:

```text
/var/run/melix/
  controlplane.sock
  worker-text-001.sock
  worker-vision-001.sock
  worker-image-001.sock
```

## Process Boundaries

### Menu Bar App

The menu bar app is a native operations surface. It should:

- Connect only to the control plane through XPC.
- Render snapshots and event-driven updates.
- Offer model pin, warmup, unload, cache purge, logs, and preset actions.
- Avoid direct access to worker sockets, cache databases, or on-disk payloads.

The dashboard is a window owned by the app, not a separate process.

### Control Plane Daemon

The control plane is the system coordinator and source of truth. It owns:

- OpenAI-compatible and Anthropic-compatible local HTTP APIs
- Request admission and scheduling
- Session, branch, and workflow metadata
- Model registry and EnginePool
- Cache metadata index
- Worker discovery and health state
- Operational flows such as doctor, bench, logs, and diagnostics

This layer should remain Swift-first because it carries the longest-lived product logic.

### Worker Pool

Workers are execution engines, not public servers. The worker plane may be implemented in multiple languages so long as it stays behind the shared worker RPC contract.

Workers own:

- Model runtime load and unload
- Prefill and decode execution
- Cache materialization and restoration
- Tool and reasoning parser glue
- Multimodal execution
- Maintenance flows such as conversion, diagnostics, and benchmarking

Workers should not expose network-facing APIs beyond local RPC.

#### Swift Text Worker

The default text generation path should move into an independent Swift text worker. In its first implementation phase it should own:

- text `Generate`
- model lifecycle for text models routed to the Swift path
- text streaming and abort
- latency-critical text runtime integration

It should not:

- run inside the control plane process
- silently fall back to the Python text path on failure
- take ownership of multimodal or maintenance families in the same phase

#### Python Workers

Python workers remain the broader execution layer. They should continue to own:

- multimodal execution
- embeddings and rerank
- image and audio families
- convert, doctor, info, and bench flows
- any text-compatible compatibility path retained during migration

### Storage Ownership

Metadata and payload ownership are split intentionally:

- Control plane owns metadata truth, scopes, summaries, and indices needed for scheduling and UI.
- Workers own materialized payloads, active decode handles, block files, and snapshot payloads.

Melix must not send large tensor or KV payloads over RPC.

## Public and Internal Interfaces

### External HTTP API

V1 should expose these local endpoints:

- `POST /v1/chat/completions`
- `POST /v1/responses`
- `POST /v1/embeddings`
- `POST /v1/rerank`
- `POST /v1/images/generations`
- `POST /v1/images/edits`
- `POST /v1/audio/transcriptions`
- `POST /v1/messages`
- `GET /v1/models`

Streaming should use SSE and support:

- content deltas
- reasoning deltas when supported
- tool-call deltas
- usage trailers
- cache trailers
- heartbeat events

Melix may accept additional local-only request fields such as:

- `session_id`
- `branch_id`
- `parent_request_id`
- `cache_policy`
- `pin_prefix`
- `save_checkpoint`
- `latency_class`
- `workflow_run_id`
- `workflow_node_id`

### Control Plane Protocol

The control plane protocol should be command-and-event oriented, versioned, and schema-driven.

The envelope should combine normalized metadata such as `command_type`, `event_type`, `source`, `correlation_id`, and `causation_id` with typed protobuf bodies for first-party command and event families. Melix should not collapse core control-plane traffic into an untyped `bytes payload` transport model.

Required XPC entry points:

- `handshake`
- `execute`
- `subscribe`
- `unsubscribe`

Command families:

- `ServerCommand`
- `ModelCommand`
- `CacheCommand`
- `SessionCommand`
- `OpsCommand`
- `PresetCommand`

Core event families:

- server state
- worker state
- model state
- request progress
- session state
- cache stats
- resource pressure
- benchmark progress
- logs

### Worker RPC

Worker RPC should be defined with gRPC over Unix Domain Sockets and cover four service groups:

- `RuntimeService` for lifecycle and model loading
- `InferenceService` for `Generate`, `Prefill`, `Decode`, `Abort`, and multimodal execution
- `CacheService` for stats, prefix pinning, snapshots, and cache purge
- `MaintenanceService` for convert, info, doctor, and bench

Melix should keep `Generate`, `Prefill`, and `Decode` because the split is required for chunked prefill, tool recovery, checkpointing, and future scheduler upgrades. These RPCs should share one underlying execution schema so tracing, metrics, scheduling hints, and event semantics remain unified.

The same RPC contract should be implementable by both Swift and Python workers. The control plane should route by worker capability and engine class rather than by implementation language assumptions.

## Request Model and Scheduling

### Request Identity

Every execution request should carry identity that supports scheduling and cache reuse:

- `request_id`
- `session_id`
- `branch_id`
- `parent_request_id`
- `workflow_run_id`
- `workflow_node_id`
- `latency_class`

These fields are not decorative. They determine queue priority, cache affinity, checkpoint scope, and tool-follow-up recovery.

The control plane should also expose session graph state, including branch lineage, active branch, head request, checkpoint state, and resume snapshot metadata.

### Queue Design

Melix should use four scheduling lanes:

- `Q0`: interactive decode, tool follow-up, immediate same-session continuation
- `Q1`: hot-prefix prefill with strong cache affinity
- `Q2`: cold or long prefill, including chunked prefill and checkpoint-friendly work
- `Q3`: background work such as embeddings, rerank, convert, bench, warmup, image, and audio tasks

The control plane protocol should expose queue read models, including lane-level queued counts, active counts, queue delay, admission latency, and backpressure.

Worker requests should also carry scheduling hints such as lane, priority, latency sensitivity, and queue delay so execution can honor control-plane intent without turning the worker into the global scheduler.

### Priority Function

Requests should be ordered with a weighted function shaped by:

- latency class
- cache affinity
- session continuity
- aging
- estimated prefill cost
- memory pressure

This prevents Melix from behaving like a simple first-come-first-served server.

### Abort and Resume

Melix must support:

- abort during queued, prefill, or decode phases
- resume from a saved boundary snapshot
- fast follow-up after tool execution

The control plane should translate cancellations into best-effort worker aborts and still produce explicit terminal request state.

## Cache Architecture

### Tier Layout

Melix uses three cache tiers:

- `L0`: active runtime state for current execution
- `L1`: in-memory shared block cache with dedup, refcounting, pinning, and copy-on-write
- `L2`: SSD-backed block and snapshot store for restart-safe reuse

This layout exists to balance hot-path latency with persistence.

### Scope and Reuse Rules

Cache reuse should be isolated by a scope that includes:

- model identity and revision
- tokenizer hash
- quantization profile
- prompt template hash
- parser mode
- reasoning mode
- multimodal adapter identity when relevant

Prompt reuse should rely on stable fingerprints and block tables rather than raw text-only matching.

The control plane should expose logical cache identity through cache keys and block or snapshot references, while keeping cache payloads worker-side.

The worker schema should define typed `CacheKey` and `BlockTable` structures so cache reuse and resume are computable protocol concepts rather than opaque identifiers.

### Pinned Prefixes

Melix should support pinning reusable prefixes for:

- system prompts
- developer prompts
- tool schemas
- fixed examples
- response format wrappers

Pinning should refer to logical cache objects, not raw prompt strings.

### Boundary Snapshots

Boundary snapshots are required for fast recovery around:

- tool calls
- long chunked prefill
- branch transitions
- hybrid-model state that cannot be reconstructed by simple prefix slicing

Snapshots and block tables must be first-class runtime concepts, not ad hoc implementation details.

## Model Lifecycle and Operations

### EnginePool

The control plane should manage models through an EnginePool that handles:

- discovery
- load and unload
- pin and unpin
- warmup
- TTL and LRU eviction
- budget-aware admission

Multi-model lifecycle is a product capability, not a worker-only implementation detail.

EnginePool should also treat engine class as a first-class routing dimension. In the next runtime phase:

- text models default to the Swift text worker
- non-text model families continue to route to Python workers
- Swift text worker failures should surface explicitly rather than silently re-route to Python

### Runtime and Maintenance

Workers should also expose operational tools as product features:

- `melix convert`
- `melix info`
- `melix doctor`
- `melix bench`

These flows should be backed by the same runtime metadata model used by the control plane.

### Quantization

V1 requires:

- offline model conversion
- quantization manifests
- KV cache q4 and q8 support at storage boundaries

The architecture should leave room for future mixed-precision and calibration extensions without redesigning core metadata formats.

Worker capability reporting should use typed core capability groups with extensible metadata rather than a flat boolean-only capability map.

## State Models

The architecture should consistently represent:

- server state: booting, ready, degraded, draining, stopped, failed
- worker state: starting, idle, busy, saturated, draining, exited, crash loop
- model state: discovered, loading, warm, pinned, evicting, unloaded, failed
- request phase: queued, prefilling, decoding, tool-wait, checkpointing, completed, aborted, failed

These states drive UI, metrics, retry behavior, and operational decisions.

In addition to lifecycle states, the control plane should expose resource snapshots for workers and server-level aggregates. At minimum these should cover CPU utilization, GPU utilization, memory used, memory total, memory budget, and active Metal memory.

## Observability and Admin

Melix should expose a coherent operational story across the menu bar app and local admin surface.

Required metrics include:

- TTFT by cold, warm, and hot path
- end-to-end latency
- queue delay
- admission latency
- queue backpressure
- prefill and decode token counts
- abort rate
- L1 and L2 hit rate
- dedup ratio
- pinned-prefix hit rate
- snapshot restore rate
- model load and warmup time
- worker memory pressure
- worker and server resource snapshots

The menu bar app is the most convenient local control surface. A local admin HTTP surface may coexist, but both must reflect the same control-plane truth.

## V1 Non-Goals

Melix V1 should explicitly avoid:

- custom compute kernels
- a built-in workflow DAG engine
- shipping tensor payloads through the control plane
- direct UI access to cache databases or worker internals
- depending on a single upstream server wrapper as the architecture boundary

## Recommended Delivery Order

The implementation should proceed in this order:

1. Repository skeleton, schemas, XPC base, worker RPC base, and menu bar shell
2. Single-model text path with streaming and in-memory cache
3. Dedicated Swift text worker for the default text `Generate` hot path
4. EnginePool depth, phase-aware text runtime behavior, queueing, and session or branch state
5. SSD-backed cache, snapshots, restart recovery, and cache inspection
6. Broader API and model families such as embeddings, rerank, vision, OCR, audio, and image flows
7. Packaging, diagnostics, and benchmark completeness

This order keeps the architecture aligned with product value: first usable, then durable, then broad.
