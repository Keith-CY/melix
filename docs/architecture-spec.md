# Melix Architecture Spec

Date: 2026-03-27

## Summary

Melix is a native control plane plus worker-runtime architecture for local AI execution on Apple Silicon. The Swift runtime baseline for the shared protocol and worker path is macOS 15 or newer. The system is built around four layers:

1. A native SwiftUI desktop app for local operations, chat, image workflows, and model tools.
2. A Swift control plane daemon that owns system truth.
3. A polyglot worker pool connected over local RPC.
4. A tiered cache and storage layer that persists reusable execution state.

The design is optimized for agent-oriented workloads: repeated prefixes, tool-call recovery, branch-aware sessions, and fast follow-up requests.

Melix should keep the control plane Swift-first while moving the latency-critical default text path toward a dedicated Swift text worker. Python workers remain the primary execution layer for multimodal, embeddings, rerank, image, audio, and maintenance flows. See `decisions/2026-03-27-swift-text-runtime.md`.

## Runtime Topology

```text
┌────────────────────────────────────────────────────────────┐
│                Melix Desktop App (SwiftUI)                │
│ dashboard, models, tools, settings, logs, bench, chat,    │
│ image, HuggingFace sync, and operator workflows           │
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

The desktop app is a native operations surface. It should:

- Connect only to the control plane through XPC.
- Render snapshots and event-driven updates.
- Offer dashboard, models, tools, settings, logs, bench, chat, and image workflows only where backend support already exists.
- Offer model pin, warmup, unload, cache purge, quantization, HuggingFace upload or download, and adapter workflows through control-plane commands.
- Avoid direct access to worker sockets, cache databases, or on-disk payloads.

The desktop product may use multiple SwiftUI windows or tabs, but it remains one app process backed by the same control-plane truth.

### Control Plane Daemon

The control plane is the system coordinator and source of truth. It owns:

- OpenAI-compatible and Anthropic-compatible local HTTP APIs
- Ollama-compatible local HTTP APIs where planned by the roadmap
- Request admission and scheduling
- Session, branch, and workflow metadata
- Model registry and EnginePool
- Cache metadata index
- Worker discovery and health state
- Operational flows such as doctor, bench, logs, diagnostics, quantization jobs, training jobs, and HuggingFace sync

This layer should remain Swift-first because it carries the longest-lived product logic.

For model discovery, the control plane owns the typed `ModelCatalog` exposed to XPC and local HTTP clients, but it should synchronize registry-discovered entries from worker-owned snapshots instead of deriving registry state from scattered per-model environment variables.

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
- convert, quantize, upload, download, train, doctor, info, and bench flows
- any text-compatible compatibility path retained during migration

MLX-backed Python text compatibility and VLM runtimes must execute model load,
warmup, prompt/template preparation, and token streaming on an executor-owned
runtime thread. The executor is responsible for initializing the MLX stream
context on that thread when MLX is available and for publishing runtime evidence
through `RuntimeStats.generation_stream_owner_mode`,
`RuntimeStats.worker_thread_init_latency_ms`, and
`RuntimeStats.stream_sync_fallback_count`. Control-plane observability should
project those fields into `python_worker.*` metrics whenever worker runtime
stats are refreshed, and it must reserve distinct numeric sentinel codes for
missing owner-mode state versus unrecognized future owner-mode strings.

Python workers also own ordered multi-root on-disk registry scanning. Registry sources are user-configured model roots first, followed by the default Hugging Face cache at `~/.cache/huggingface/hub` when it exists. Root order is significant, the first root wins on duplicate `model_id`, and invalid roots must not poison discovery from valid roots. Scanning recognizes Hugging Face cache snapshots at `models--<org>--<repo>/snapshots/<snapshot-id>` and plain local MLX model directories that contain `config.json` plus model weights. The scanner must skip Hugging Face `blobs` payloads and must not load the MLX runtime during discovery.

Melix-managed Hugging Face downloads write model bytes directly into `~/.cache/huggingface/hub` by passing that path as `snapshot_download(cache_dir=...)`; `HUGGINGFACE_HUB_CACHE` and `HF_HOME` do not change the Melix-managed download location. New Hub downloads no longer create registry descriptors under `MELIX_MANAGED_MODEL_ROOT`, and download receipts report the real runtime snapshot path. Registry metadata for cache/root-discovered models exposes `melix.model_path`, `melix.source_kind=hf_cache_snapshot` or `local_mlx_directory`, `melix.registry_root_path`, and `melix.registry_relative_path`; Hugging Face cache snapshots also expose `melix.hf_repo_id` and `melix.hf_revision`. Cache/root-discovered models do not expose `melix.registry_descriptor_path`. If a Hugging Face snapshot is deleted and the registry is rescanned, the model disappears instead of entering a descriptor-driven missing-cache state. Legacy descriptor scanning remains only as a compatibility path for older managed roots that are still configured.

Registry discovery is intentionally MLX-only. A model is published only when repo identity, README/card metadata, tags, `library_name`, file metadata, or local path naming provides an explicit MLX signal. Non-MLX Transformers repositories, unreadable directories, and ambiguous local model folders are hidden.

Hugging Face download tokens are stored by the Swift CLI/Desktop layer in `$MELIX_HOME/secrets/huggingface-token.json` with private directory and file permissions. The token is sent to the worker only as a transient request `ext` value for `snapshot_download(token=...)`; token-like values must be redacted from operation state, manifests, registry metadata, `/v1/models`, logs, and UI surfaces. Hugging Face 401/403 failures map to `hf_auth_failed` with message `Hugging Face authentication failed. Check your token and try again.` Local imports remain copied into `MELIX_MANAGED_MODEL_ROOT/local/<model-id>/<revision>`.

### Storage Ownership

Metadata and payload ownership are split intentionally:

- Control plane owns metadata truth, scopes, summaries, and indices needed for scheduling and UI.
- Workers own materialized payloads, active decode handles, block files, and snapshot payloads.

Melix must not send large tensor or KV payloads over RPC.

## Public and Internal Interfaces

### External HTTP API

V1 should expose these local endpoints:

- `POST /v1/chat/completions`
- `POST /v1/completions`
- `POST /v1/responses`
- `POST /v1/embeddings`
- `POST /v1/rerank`
- `POST /v1/images/generations`
- `POST /v1/images/edits`
- `POST /v1/audio/transcriptions`
- `POST /v1/audio/speech`
- `POST /v1/messages`
- `GET /v1/models`
- `GET /v1/cache/stats`
- `GET /health`

The gateway should also leave room for Ollama-compatible local endpoints such as:

- `POST /api/chat`
- `POST /api/generate`
- `GET /api/tags`
- `POST /api/show`
- `POST /api/embeddings`

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

The control-plane and worker protocols should use explicit lane identifiers rather than exporting the `Q0-Q3` shorthand directly:

- `Q0` maps to `text.decode.interactive`
- `Q1` maps to `text.prefill.hot`
- `Q2` maps to `text.prefill.background`
- `Q3` remains the conceptual background lane family for later non-text phases

The control plane protocol should expose queue read models, including lane-level queued counts, active counts, queue delay, admission latency, and backpressure.

Worker requests should also carry scheduling hints such as lane, priority, latency sensitivity, and queue delay so execution can honor control-plane intent without turning the worker into the global scheduler.

The current continuous-batching baseline should be enabled only on the Swift text route and only for phase-aware prefill work. Batch cohorts should be keyed by route, model, prefill lane, and cache-affinity class so hot and restored work do not collapse into the same admission group accidentally. Admission fairness should remain FIFO across cohorts: a compatible request may join the active batch only while no earlier incompatible work is already queued.

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
- `L1`: in-memory shared prefix and paged block cache with dedup, refcounting, pinning, and copy-on-write
- `L2`: SSD-backed block and snapshot store for restart-safe reuse

This layout exists to balance hot-path latency with persistence.

The default cache mode should remain `tiered`, which means `L1` plus `L2` reuse without experimental eviction or rolling-window behavior. Melix should also reserve explicit protocol-visible cache modes for experimental long-context execution:

- `rotating`: a rolling active-window strategy for long decode paths where earlier KV state may be compacted behind a stable restore boundary
- `hybrid`: a mixed strategy that keeps tiered prefix reuse while allowing a rotating active window for the tail of execution

These modes should be visible in runtime policy and cache metrics before they become default execution behavior. Experimental modes must remain opt-in until benchmark and recovery evidence are stable.

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

The worker schema should define typed `CacheKey` and `BlockTable` structures so cache reuse and resume are computable protocol concepts rather than opaque identifiers. KV cache quantization should happen at the storage boundary so active execution can stay accuracy-aware while persisted cache assets remain space-efficient.

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
- model aliasing and type overrides
- per-model sampling and template policy
- acceleration profile selection
- HuggingFace import and export workflows

Multi-model lifecycle is a product capability, not a worker-only implementation detail.

EnginePool should also treat engine class as a first-class routing dimension. In the next runtime phase:

- text models default to the Swift text worker
- non-text model families continue to route to Python workers
- Swift text worker failures should surface explicitly rather than silently re-route to Python

### Runtime and Maintenance

Workers should also expose operational tools as product features:

- `melix convert`
- `melix quantize`
- `melix upload`
- `melix download`
- `melix train`
- `melix info`
- `melix doctor`
- `melix bench`

These flows should be backed by the same runtime metadata model used by the control plane.

### Agentic Tool Runtime

Agentic training replay, online rollout, benchmark, and evaluation must share one
worker-owned tool registry contract. The initial built-in registry lives in the
Python worker runtime and exports deterministic OpenAI-compatible function
schemas plus Melix `ToolConfig` metadata for image crop, layout parsing, text
search, image search, visit, and local compute tools. The registry is a contract
boundary only: concrete adapters, observation redaction, replay metadata, and
evaluation routing are layered on top in separate implementation slices.

### Quantization

V1 requires:

- offline model conversion
- advanced quantization manifests and profiles
- quantization manifests
- KV cache q4 and q8 support at storage boundaries
- a path for lower-bit and mixed-precision cache or model quantization profiles

Worker maintenance flows should also leave room for:

- artifact upload to HuggingFace
- artifact download from HuggingFace
- LoRA and QLoRA adapter packaging
- calibration and validation reports

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
- speculative decode acceptance and rollback rate
- cache quantization compression ratio
- HuggingFace transfer timings
- quantization and training job duration

The menu bar app is the most convenient local control surface. A local admin HTTP surface may coexist, but both must reflect the same control-plane truth.

Image generation belongs in dedicated worker families that may wrap a specialized runtime distinct from the text or analysis runtimes. By contrast, backend capabilities such as quantized matrix multiplication and SDPA remain runtime assumptions provided by the selected MLX stack rather than first-class control-plane modules.

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
6. Broader API, desktop operations, and model workflows such as embeddings, rerank, desktop panels, HuggingFace sync, and quantization
7. Multimodal families such as vision, OCR, audio, and image flows
8. Packaging, diagnostics, training workflows, and benchmark completeness

This order keeps the architecture aligned with product value: first usable, then durable, then broad.
