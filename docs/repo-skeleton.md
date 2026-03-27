# Melix Repository Skeleton

Date: 2026-03-27

## Summary

This document defines the recommended monorepo structure for Melix. The goal is to make the repository match the product and architecture documents directly, so the first implementation pass does not need to invent top-level boundaries.

The repository should reflect four long-lived assets:

- native macOS app surfaces
- Swift control plane and gateway logic
- Python inference workers
- cross-language protocol, tools, and operational assets

This skeleton is optimized for a Swift-first control plane, a dedicated Swift text worker, MLX-backed Python workers for broader execution families, agent-aware cache and scheduling, and a native macOS runtime experience.

## Top-Level Structure

```text
melix/
├─ README.md
├─ LICENSE
├─ Makefile
├─ Brewfile
├─ .editorconfig
├─ .gitignore
├─ .github/
│  ├─ workflows/
│  ├─ ISSUE_TEMPLATE/
│  └─ pull_request_template.md
│
├─ Package.swift
├─ pyproject.toml
├─ uv.lock
├─ buf.yaml
├─ buf.gen.yaml
│
├─ apps/
│  ├─ macos-menubar/
│  │  ├─ Package.swift
│  │  ├─ Sources/
│  │  │  ├─ AppMain/
│  │  │  ├─ MenuBar/
│  │  │  ├─ Dashboard/
│  │  │  ├─ Models/
│  │  │  ├─ Tools/
│  │  │  ├─ Settings/
│  │  │  ├─ Bench/
│  │  │  ├─ Sessions/
│  │  │  ├─ Chat/
│  │  │  ├─ Image/
│  │  │  ├─ APIReference/
│  │  │  ├─ CacheInspector/
│  │  │  ├─ Logs/
│  │  │  ├─ HuggingFace/
│  │  │  ├─ Training/
│  │  │  └─ XPCClient/
│  │  ├─ Resources/
│  │  └─ Tests/
│  │
│  └─ admin-web/
│     ├─ package.json
│     ├─ bun.lock
│     ├─ src/
│     └─ dist/
│
├─ services/
│  ├─ control-plane-swift/
│  │  ├─ Package.swift
│  │  ├─ Sources/
│  │  │  ├─ Bootstrap/
│  │  │  ├─ HTTPGateway/
│  │  │  │  ├─ OpenAI/
│  │  │  │  ├─ Anthropic/
│  │  │  │  ├─ Responses/
│  │  │  │  ├─ Embeddings/
│  │  │  │  ├─ Images/
│  │  │  │  ├─ Audio/
│  │  │  │  ├─ Rerank/
│  │  │  │  └─ SSE/
│  │  │  ├─ XPCService/
│  │  │  ├─ WorkerRegistry/
│  │  │  ├─ WorkerClient/
│  │  │  ├─ EnginePool/
│  │  │  ├─ Scheduler/
│  │  │  │  ├─ Queues/
│  │  │  │  ├─ Admission/
│  │  │  │  ├─ Affinity/
│  │  │  │  └─ Priorities/
│  │  │  ├─ Sessions/
│  │  │  ├─ WorkflowBridge/
│  │  │  ├─ CacheIndex/
│  │  │  ├─ PrefixPinning/
│  │  │  ├─ Checkpoints/
│  │  │  ├─ ModelCatalog/
│  │  │  ├─ Presets/
│  │  │  ├─ Metrics/
│  │  │  ├─ Logs/
│  │  │  ├─ Security/
│  │  │  └─ Admin/
│  │  └─ Tests/
│  │
│  ├─ mlx-text-worker-swift/
│  │  ├─ Package.swift
│  │  ├─ Sources/
│  │  │  ├─ Bootstrap/
│  │  │  ├─ RPCServer/
│  │  │  ├─ Runtime/
│  │  │  ├─ Engine/
│  │  │  ├─ Models/
│  │  │  ├─ Streaming/
│  │  │  ├─ Abort/
│  │  │  └─ Metrics/
│  │  └─ Tests/
│  │
│  └─ mlx-worker-python/
│     ├─ pyproject.toml
│     ├─ worker/
│     │  ├─ bootstrap.py
│     │  ├─ grpc_server.py
│     │  ├─ registry.py
│     │  ├─ runtime/
│     │  │  ├─ driver.py
│     │  │  ├─ mlx_text_runtime.py
│     │  │  ├─ mlx_hybrid_runtime.py
│     │  │  ├─ mlx_vlm_runtime.py
│     │  │  ├─ mlx_embedding_runtime.py
│     │  │  ├─ image_runtime.py
│     │  │  └─ audio_runtime.py
│     │  ├─ engine/
│     │  │  ├─ engine_core.py
│     │  │  ├─ simple_engine.py
│     │  │  ├─ batched_engine.py
│     │  │  ├─ hybrid_engine.py
│     │  │  ├─ stream_mux.py
│     │  │  ├─ output_collector.py
│     │  │  └─ request_state.py
│     │  ├─ scheduler/
│     │  │  ├─ phase_scheduler.py
│     │  │  ├─ batch_builder.py
│     │  │  ├─ decode_lane.py
│     │  │  ├─ prefill_lane.py
│     │  │  └─ admission.py
│     │  ├─ cache/
│     │  │  ├─ scope.py
│     │  │  ├─ prefix_index.py
│     │  │  ├─ block_table.py
│     │  │  ├─ in_memory_cache.py
│     │  │  ├─ ssd_store.py
│     │  │  ├─ snapshot_store.py
│     │  │  ├─ recovery.py
│     │  │  ├─ quantized_kv.py
│     │  │  └─ stats.py
│     │  ├─ parsers/
│     │  │  ├─ tool_parsers/
│     │  │  ├─ reasoning_parsers/
│     │  │  └─ auto_config.py
│     │  ├─ multimodal/
│     │  │  ├─ images.py
│     │  │  ├─ audio.py
│     │  │  └─ processors.py
│     │  ├─ quant/
│     │  │  ├─ convert.py
│     │  │  ├─ profiles.py
│     │  │  ├─ manifests.py
│     │  │  ├─ calibration.py
│     │  │  ├─ uploader.py
│     │  │  ├─ downloader.py
│     │  │  ├─ doctor.py
│     │  │  └─ bench.py
│     │  ├─ training/
│     │  │  ├─ lora.py
│     │  │  ├─ qlora.py
│     │  │  ├─ adapters.py
│     │  │  └─ jobs.py
│     │  ├─ model_registry/
│     │  └─ utils/
│     └─ tests/
│
├─ packages/
│  ├─ protocol/
│  │  ├─ schema/
│  │  │  ├─ controlplane/v1/control_plane.proto
│  │  │  ├─ worker/v1/common.proto
│  │  │  ├─ worker/v1/runtime.proto
│  │  │  ├─ worker/v1/inference.proto
│  │  │  ├─ worker/v1/cache.proto
│  │  │  └─ worker/v1/maintenance.proto
│  │  ├─ swift/
│  │  └─ python/
│  │
│  ├─ client-presets/
│  │  ├─ claude-code/
│  │  ├─ cursor/
│  │  ├─ aider/
│  │  ├─ continue/
│  │  └─ open-webui/
│  │
│  ├─ benchmark-suite/
│  │  ├─ latency/
│  │  ├─ tool-calling/
│  │  ├─ long-context/
│  │  ├─ multimodal/
│  │  └─ model-switching/
│  │
│  └─ fixtures/
│     ├─ prompts/
│     ├─ tool_schemas/
│     ├─ images/
│     └─ audio/
│
├─ tools/
│  ├─ convert-cli/
│  ├─ quantize-cli/
│  ├─ upload-cli/
│  ├─ download-cli/
│  ├─ train-cli/
│  ├─ doctor-cli/
│  ├─ bench-cli/
│  ├─ model-downloader/
│  ├─ model-uploader/
│  ├─ cache-inspector/
│  └─ log-bundle/
│
├─ infra/
│  ├─ launchd/
│  │  ├─ com.melix.controlplane.plist
│  │  └─ com.melix.worker-template.plist
│  ├─ packaging/
│  ├─ dmg/
│  ├─ homebrew/
│  └─ signing/
│
├─ docs/
│  ├─ product-brief.md
│  ├─ architecture-spec.md
│  ├─ control-plane-protocol.md
│  ├─ worker-rpc-schema.md
│  └─ repo-skeleton.md
│
└─ third_party/
   └─ patches/
```

## Directory Responsibilities

### `apps/macos-menubar/`

This is the user-facing native shell. It should own:

- the menu bar entry point
- dashboard, models, tools, settings, logs, bench, chat, and image windows or tabs
- model, cache, HuggingFace, quantization, and training controls only where backend support already exists
- recent runtime status and operator workflows
- XPC client bindings to the control plane

It must not:

- call workers directly
- own model state truth
- read or write cache internals on disk

### `apps/admin-web/`

This is optional and should exist only if a local admin web surface is needed. If it exists, Node package management should use Bun rather than npm or pnpm.

### `services/control-plane-swift/`

This is the long-lived product core. It should own:

- local HTTP and SSE gateway behavior
- XPC service implementation
- request scheduling and admission
- EnginePool and model lifecycle
- session, branch, and checkpoint metadata
- cache summaries and indices
- worker registry and RPC clients
- metrics, logs, diagnostics, presets, and admin logic

It must not:

- run model kernels directly
- keep large active tensor payloads
- collapse modality-specific execution details into gateway handlers

### `services/mlx-text-worker-swift/`

This is the latency-critical text execution service. It should own:

- the default text `Generate` hot path
- text-model lifecycle for models routed to the Swift engine class
- text streaming and abort
- text-runtime metrics and diagnostics

It must not:

- run inside the control plane process
- take ownership of multimodal, embeddings, rerank, image, audio, or maintenance families in its first phase
- silently delegate failed text execution to the Python path

### `services/mlx-worker-python/`

This is the broader execution layer. It should own:

- MLX runtime bindings
- multimodal, embedding, rerank, image, and audio execution
- maintenance-compatible text or migration paths retained during runtime transition
- prefill and decode flow
- L0 and L1 hot-path cache handling
- asynchronous writes into L2 storage
- tool and reasoning parser glue
- convert, quantize, upload, download, training, doctor, info, and benchmark behaviors

It must not:

- define global eviction policy
- serve UI-facing APIs
- own session or workflow truth

### `packages/protocol/`

This is the cross-language contract layer. Every XPC payload, gRPC request, reply, and stream event should be generated from schema here.

### `packages/client-presets/`

This is a product compatibility asset directory. It should contain client-specific presets, parser preferences, timeout defaults, and request-shape quirks for supported local clients.

### `tools/`

This directory should contain standalone operator-facing tools, not hidden helper scripts embedded only in server startup paths.

## Core Modules

| Module | Owner | Responsibility |
|---|---|---|
| `EnginePool` | control plane | multi-model load, pin, TTL, LRU, memory-aware admission |
| `Scheduler` | control plane | queue lanes, cache affinity, aging, admission, phase-aware dispatch |
| `SessionRegistry` | control plane | session, branch, workflow-run, and checkpoint identities |
| `CacheIndex` | control plane | cache metadata truth, summaries, logical prefix and snapshot indices |
| `WorkerClient` | control plane | gRPC client wrappers and streaming bridges |
| `TextEngine` | swift text worker | default text generation, abort, runtime integration, stream emission |
| `EngineCore` | worker | runtime execution, scheduling handoff, cache manager orchestration |
| `InMemoryBlockCache` | worker | L1 block pool, dedup, refcounting, copy-on-write, pinning |
| `SSDStore` | worker | durable block and snapshot payload storage |
| `ToolParser` | worker | tool-call normalization into internal IR |
| `ReasoningParser` | worker | reasoning separation logic |
| `QuantPipeline` | worker | convert, manifests, calibration hooks, uploader, downloader, doctor, bench |
| `TrainingJobs` | worker | LoRA or QLoRA job execution, adapter packaging, training metrics |
| `MenuBarClient` | app | XPC calls, subscriptions, and UI state refresh |

## Process Boundaries

The repository layout must reinforce the runtime boundaries:

```text
Menu Bar App
  └─ XPC ──> Control Plane Daemon
                ├─ HTTP/SSE ──> local API clients
                └─ gRPC over UDS ──> Swift and Python Workers
```

Rules:

1. UI does not talk to workers.
2. Workers do not expose public HTTP APIs.
3. Cross-language contracts are generated from `packages/protocol`.
4. Cache metadata lives with the control plane.
5. Cache payloads live with workers.
6. Dashboard and menu bar use the same control-plane snapshot truth.

## Build and Release Artifacts

### Development Outputs

- `swift build` for the control plane, protocol consumers, and menu bar app
- `swift build` for the Swift text worker
- `uv sync` and `pytest` for the Python worker
- `buf generate` for schema outputs
- `make dev-up` to boot the control plane, the default text worker, and the menu bar app in a local development loop
- `make bench` for latency, cache, and model-switching measurements

### Delivery Outputs

- `melix.dmg` containing the native app, helper configuration, and packaged runtime metadata
- `melix` CLI for development and operations
- launchd configuration for the control plane
- packaged Swift text worker runtime
- packaged Python worker runtime
- optional Homebrew formula

## Local Commands and CI

### Local Commands

```bash
make bootstrap
make proto
make swift-test
make py-test
make integration-test
make bench
make package
```

These commands should remain stable over time because they become team muscle memory and CI primitives.

### CI Layers

1. `lint`
2. `proto-compat`
3. `swift-unit`
4. `python-unit`
5. `integration`
6. `perf-smoke`
7. `package-smoke`

## First Files to Implement

### Swift Control Plane

- `services/control-plane-swift/Sources/Bootstrap/main.swift`
- `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- `services/control-plane-swift/Sources/WorkerClient/WorkerClient.swift`
- `services/control-plane-swift/Sources/EnginePool/EnginePool.swift`
- `services/control-plane-swift/Sources/Scheduler/RequestScheduler.swift`
- `services/control-plane-swift/Sources/CacheIndex/CacheIndexStore.swift`
- `services/control-plane-swift/Sources/Sessions/SessionRegistry.swift`

### Swift Text Worker

- `services/mlx-text-worker-swift/Sources/Bootstrap/main.swift`
- `services/mlx-text-worker-swift/Sources/RPCServer/WorkerServer.swift`
- `services/mlx-text-worker-swift/Sources/Runtime/TextRuntime.swift`
- `services/mlx-text-worker-swift/Sources/Engine/TextEngine.swift`
- `services/mlx-text-worker-swift/Sources/Streaming/TokenStreamWriter.swift`
- `services/mlx-text-worker-swift/Sources/Abort/AbortRegistry.swift`

### Python Worker

- `services/mlx-worker-python/worker/grpc_server.py`
- `services/mlx-worker-python/worker/engine/engine_core.py`
- `services/mlx-worker-python/worker/runtime/mlx_text_runtime.py`
- `services/mlx-worker-python/worker/cache/in_memory_cache.py`
- `services/mlx-worker-python/worker/cache/ssd_store.py`
- `services/mlx-worker-python/worker/cache/prefix_index.py`
- `services/mlx-worker-python/worker/quant/convert.py`
- `services/mlx-worker-python/worker/parsers/auto_config.py`

### Protocol Layer

- `packages/protocol/schema/controlplane/v1/control_plane.proto`
- `packages/protocol/schema/worker/v1/runtime.proto`
- `packages/protocol/schema/worker/v1/inference.proto`
- `packages/protocol/schema/worker/v1/cache.proto`
- `packages/protocol/schema/worker/v1/maintenance.proto`

## Explicit Non-Goals for the Initial Repo Pass

Do not front-load these into the first repository phase:

- custom compute kernels
- a custom default model format
- a built-in workflow DAG engine
- tensor or block payload handling inside the control plane
- direct UI access to cache metadata storage
- dependence on a single upstream server wrapper as the architecture boundary

## Recommended Delivery Order

### Phase 0: Skeleton

- create the monorepo
- add schema layout
- add XPC hello world
- add gRPC-over-UDS hello world
- add menu bar shell
- add empty text-worker shell

### Phase 1: Single-Model Usable Path

- default text route moved to the Swift text worker
- `POST /v1/chat/completions` through the Swift text `Generate` path
- SSE streaming and `Abort`
- explicit failure on Swift text worker errors rather than silent Python fallback
- menu bar server-state and model-state view

### Phase 2: System Usable Path

- real `Prefill` and `Decode`
- multi-model EnginePool depth
- four-lane scheduler
- session and branch registry
- tool and reasoning parser support

### Phase 3: Durable Cache Assets

- SSD block store
- SQLite WAL metadata
- checkpoints and boundary snapshots
- cache inspector
- restart recovery

### Phase 4: Text API and Desktop Foundation

- `POST /v1/completions`
- `POST /v1/responses`
- `POST /v1/messages`
- dashboard, settings, logs, bench, and API reference foundation
- health and operator status surfaces

### Phase 5: Retrieval and Model Operations

- embeddings
- rerank
- per-model settings
- quantization and conversion workflows
- HuggingFace download and upload
- cache stats and operator model workflows

### Phase 6: Multimodal Analysis and Chat Product Surface

- vision and OCR
- audio transcription and speech
- native chat panel

### Phase 7: Image Workloads and Image Product Surface

- image generation and editing
- native image panel
- artifact workflows

### Phase 8: Training and Release Completion

- LoRA and QLoRA workflows
- packaging and startup automation
- convert, doctor, info, and bench completeness

## Repository Conventions

- Bun is the default package manager for local JavaScript or TypeScript surfaces.
- Python dependency and test workflows should prefer `uv`.
- Schema generation should be reproducible and committed through the repo’s normal build flow.
- New public contracts should land in `packages/protocol` before any handwritten ad hoc transport glue is added elsewhere.
- Operational tools should remain callable outside the UI so development and support flows are not trapped behind the menu bar app.
