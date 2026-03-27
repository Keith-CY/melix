# Post-Phase-0 Coding Milestones

> **For agentic workers:** Use this document as the execution-order companion to the phase implementation plans. Start from the milestone ladder here, then open the linked phase plan for subsystem detail before editing code.

**Goal:** Decompose the remaining Melix roadmap into coding-sized milestones that can be landed, tested, benchmarked, and reviewed in small slices without reopening phase-level design questions.

**Scope:** This document covers `Phase 1` through `Phase 8`. `Phase 0` is already complete and remains documented in `plans/2026-03-27-phase-0-thin-path.md`.

## How To Use This Document

- Treat each milestone as the preferred landing slice for one implementation branch or one tightly related commit stack.
- Use the linked phase implementation plan as the source of subsystem detail, file targets, and non-goals.
- Do not declare a milestone complete without the verification and metrics evidence listed in the corresponding phase plan.
- Keep deterministic execution as the default integration path until the milestone explicitly enables a stable live path.

## Sequencing Rules

- Finish the milestone ladder for the active phase before starting endpoint or UI work from later phases.
- Do not widen the public API surface ahead of worker routing and runtime support.
- Do not add operator workflows until the backend state and metrics they depend on already exist.
- Preserve the existing public HTTP and XPC surface unless the active phase explicitly expands it.

## Phase 1: Swift Text Worker Hot Path

Detailed plan:

- `plans/2026-03-27-phase-1-swift-text-worker.md`

Target outcome:

- the default text `Generate` path runs through an independent Swift text worker, while Python remains the execution path for non-text families

| Milestone | Focus | Main Outputs | Exit Gate |
| --- | --- | --- | --- |
| `P1-M1` | Protocol and package baseline | Swift worker RPC code generation, shared Swift protocol package updates, build integration | `make proto` succeeds and Swift packages import generated worker stubs without manual transport duplicates |
| `P1-M2` | Swift worker service scaffold | `mlx-text-worker-swift` bootstrap, RPC server shell, runtime registry, abort registry, metrics store | worker process boots independently and returns coherent `Handshake` plus structured `unimplemented` for unsupported RPCs |
| `P1-M3` | Runtime lifecycle | MLX-backed model load, unload, list, and stats for `melix-dev-text` with `MELIX_DEV_TEXT_MODEL_PATH` override | worker lifecycle tests pass and live model loading works against a configured dev model |
| `P1-M4` | Generate and abort | streamed `Generate`, in-flight `Abort`, TTFT and TPS probes, terminal event correctness | worker-only smoke shows token streaming and clean cancellation with metrics captured |
| `P1-M5` | Control-plane routing | engine-aware worker registry, native Swift worker client, text route selection, explicit route failure behavior | `/v1/chat/completions` and `/v1/models` use the Swift worker by default without API shape changes |
| `P1-M6` | Workflow and evidence | local dev scripts, integration coverage, Python-path comparison harness, required hot-path metrics report | touched scope stays at or above `95%` coverage and Swift-vs-Python hot-path metrics are recorded |

## Phase 2: Text Runtime Depth and Acceleration

Detailed plan:

- `plans/2026-03-27-phase-2-text-runtime-depth.md`

Target outcome:

- text execution becomes phase-aware, acceleration-aware, queue-aware, and observable rather than a single opaque `Generate` flow

| Milestone | Focus | Main Outputs | Exit Gate |
| --- | --- | --- | --- |
| `P2-M1` | Phase-aware protocol shapes | request lifecycle states, queue and admission metadata, `Prefill` and `Decode` message updates, control-plane event expansion | generated schemas compile and control-plane tests can represent queued, prefill, decode, and terminal phases |
| `P2-M2` | Scheduler lane read model | queue lanes, admission policy, priority hints, backpressure state, request progress snapshots | control-plane unit tests cover lane assignment and queue-state reporting |
| `P2-M3` | Prefill runtime | Swift worker `Prefill` implementation, prompt-processing checkpoints, prefill metrics probes | worker tests prove prefill can run and expose reusable intermediate state |
| `P2-M4` | Decode and speculative runtime | Swift worker `Decode`, draft-model speculative decode, throughput and acceptance probes | resumed decode path streams correctly and speculative mode is benchmarked |
| `P2-M5` | Accelerated prefill and active KV mode | accelerated-prefill or prompt-lookup mode plus active-path KV-cache quantization policy | repetitive structured prompts show measurable prefill gain without breaking correctness |
| `P2-M6` | Abort and observability | abort across queued, prefill, and decode phases; richer request progress and scheduler metrics | integration tests cover cancellation from every lifecycle phase and report queue plus phase timings |
| `P2-M7` | Operator and benchmark evidence | local queue-pressure workflow, updated smoke scripts, phase-aware metrics report | admission latency, queue delay, TTFT, TPS, abort latency, and acceleration metrics are all measured and non-`N/A` |

## Phase 3: Unified Cache, Session Graph, and Recovery

Detailed plan:

- `plans/2026-03-27-phase-3-cache-session-recovery.md`

Target outcome:

- reuse, branch-aware session state, and recovery move from planned abstractions into observable runtime behavior

| Milestone | Focus | Main Outputs | Exit Gate |
| --- | --- | --- | --- |
| `P3-M1` | Cache and session contracts | cache keys, block tables, snapshot refs, session graph and branch state in shared protocols | schema generation and control-plane models represent cache and branch metadata without placeholder gaps |
| `P3-M2` | Hot-tier cache primitives | worker cache metadata store, prefix or paged cache ownership, block tables, reuse stats | worker tests can persist and reload hot-tier cache metadata for one model handle |
| `P3-M3` | Disk and quantized cache tier | disk-backed block store, restore path, storage-boundary cache quantization, compression stats | durable restore works and quantized cache footprint is measurable |
| `P3-M4` | Session graph state | control-plane session graph store, active branch tracking, resume metadata, branch lineage transitions | control-plane tests cover branch creation, selection, and resume metadata hydration |
| `P3-M5` | Recovery flows | checkpoint save policy, snapshot restore path, request resume semantics across tool boundaries | follow-up and restart-aware recovery paths pass integration tests |
| `P3-M6` | Cache-aware scheduling | prefix affinity, warm-route preference, reuse-aware admission decisions, cache pressure reporting | follow-up requests show measurable TTFT improvement versus cold baselines |
| `P3-M7` | Recovery evidence and operator path | restart smoke, cache inspection surface, recovery metrics report | hit rate, restore latency, compression ratio, TTFT delta, and cache footprint are recorded |

## Phase 4: Text API Breadth and Desktop Ops Foundation

Detailed plan:

- `plans/2026-03-27-phase-4-text-api-breadth-agent-semantics.md`

Target outcome:

- Melix supports the next text endpoint family without diverging runtime semantics across clients

| Milestone | Focus | Main Outputs | Exit Gate |
| --- | --- | --- | --- |
| `P4-M1` | Endpoint contract alignment | request and response models for `/v1/completions`, `/v1/responses`, and `/v1/messages`, translation invariants, shared stream framing rules | protocol and translator tests define consistent cross-endpoint behavior |
| `P4-M2` | Responses endpoint | control-plane translator, HTTP handler, streaming support, endpoint-specific usage and finish mapping | `/v1/responses` passes unit and integration coverage with the existing text runtime |
| `P4-M3` | Completions and messages endpoints | control-plane translators, handlers, and state threading for `/v1/completions` and `/v1/messages` | both endpoints are live and test-covered without breaking chat or responses |
| `P4-M4` | Reasoning and tool deltas | normalized reasoning chunks, tool-call delta framing, endpoint-invariant event ordering | stream-fidelity tests validate reasoning and tool deltas across all text endpoints |
| `P4-M5` | Workflow-aware shaping | preset selection, workflow metadata, request normalization, session and branch continuity across endpoints | phase-specific request shaping behaves consistently for the same logical session |
| `P4-M6` | Native desktop foundation | dashboard, models, settings, logs, bench, and API reference foundation over control-plane truth | the desktop shell exposes real operator state rather than placeholders |
| `P4-M7` | Endpoint and desktop evidence | endpoint-by-endpoint smoke, translation overhead report, stream latency report, desktop action report | translation latency, stream-fidelity, and desktop action metrics are recorded |

## Phase 5: Embeddings, Rerank, and Model Operations

Detailed plan:

- `plans/2026-03-27-phase-5-embeddings-rerank.md`

Target outcome:

- the first non-generative worker classes land without eroding text responsiveness

| Milestone | Focus | Main Outputs | Exit Gate |
| --- | --- | --- | --- |
| `P5-M1` | Capability and settings model | capability metadata, model catalog typing, per-model settings, worker route classes | catalog and protocol tests distinguish text, embeddings, rerank, and model-ops routes cleanly |
| `P5-M2` | Embeddings runtime | Python embedding worker path, model load lifecycle, batch handling, throughput probes | worker tests and smoke requests produce stable embedding outputs |
| `P5-M3` | Rerank runtime | Python rerank path, scoring output model, candidate-window handling, latency probes | rerank worker tests cover scoring correctness and terminal error behavior |
| `P5-M4` | Model-ops backend | quantization, conversion, downloader, uploader, manifests, and operator-safe job state | quantization and transfer jobs run through stable maintenance paths |
| `P5-M5` | Control-plane endpoints and workflows | `/v1/embeddings`, `/v1/rerank`, route selection, cache stats, health, and model-ops commands | endpoints and operator workflows are live without changing the text hot path |
| `P5-M6` | Native model tools | desktop Models and Tools workflows for settings, quantization, download, and upload | the desktop shell drives real model-ops behavior through the control plane |
| `P5-M7` | Mixed-workload and model-ops evidence | mixed-load integration suite, operator smoke, throughput, interference, and model-ops report | embeddings throughput, rerank latency, text interference, and model-ops metrics are recorded |

## Phase 6: Vision, OCR, Audio, and Chat Panel

Detailed plan:

- `plans/2026-03-27-phase-6-vision-ocr-audio-transcription.md`

Target outcome:

- multimodal analysis capabilities arrive with dedicated preprocessing, routing, and isolation

| Milestone | Focus | Main Outputs | Exit Gate |
| --- | --- | --- | --- |
| `P6-M1` | Multimodal contracts | image and audio input normalization rules, capability typing, OCR/VLM/transcription/speech protocol surfaces | protocol and request-normalization tests cover accepted multimodal payload shapes |
| `P6-M2` | OCR and VLM runtime | Python preprocessing adapters, OCR runtime, VLM inference path, memory probes | worker smoke covers OCR extraction and one image-to-text VLM path |
| `P6-M3` | Audio runtime | audio preprocessing, transcription and speech worker runtimes, response mapping | audio tests cover file handling, chunking, final transcript output, and speech output |
| `P6-M4` | Control-plane routing and endpoint surface | multimodal route selection, `/v1/audio/transcriptions`, `/v1/audio/speech`, model visibility updates | audio endpoints are live and multimodal analysis requests route correctly |
| `P6-M5` | Native Chat panel | chat history, reasoning, tool-call visibility, and multimodal-aware chat workflows | the desktop Chat panel reflects real control-plane and runtime state |
| `P6-M6` | Isolation and observability | background lanes for multimodal analysis, text-protection policy, preprocessing metrics and pressure reporting | text responsiveness remains stable under OCR/VLM/audio traffic |
| `P6-M7` | Integration and operator workflows | multimodal dev smoke, runbooks, latency and memory report | OCR latency, transcription latency, speech latency, VLM first-token latency, and preprocessing memory spikes are recorded |

## Phase 7: Image Generation, Image Editing, and Image Panel

Detailed plan:

- `plans/2026-03-27-phase-7-image-generation-editing.md`

Target outcome:

- long-running image jobs become a first-class workload with explicit progress, artifacts, and cancellation

| Milestone | Focus | Main Outputs | Exit Gate |
| --- | --- | --- | --- |
| `P7-M1` | Image job contracts | job state model, artifact metadata, image request and response contracts, cancellation semantics | protocol generation and control-plane tests cover queued, running, canceled, failed, and completed image jobs |
| `P7-M2` | Generation runtime | Python image generation worker path, job execution shell, progress probes, output artifact persistence | worker smoke produces a generation artifact and reports progress updates |
| `P7-M3` | Edit runtime | image edit and mask-handling runtime, artifact lineage, edit-specific validation | edit worker tests cover input validation, artifact emission, and failure paths |
| `P7-M4` | Control-plane job orchestration | `/v1/images/generations`, `/v1/images/edits`, job tracking, artifact lookup, operator-visible job state | both image endpoints are live with explicit long-running job state |
| `P7-M5` | Native Image panel | generation, edit, preview, artifact, and progress workflows in the desktop app | the Image panel drives real jobs through control-plane state only |
| `P7-M6` | Isolation and cancellation | background pool isolation, cancel path hardening, queue-pressure metrics | image traffic does not collapse text responsiveness and cancellation is reliable |
| `P7-M7` | Integration and operator evidence | artifact smoke tests, operator flows, latency and resource report | image latency, queue wait, cancel success, artifact publish, and peak resource metrics are recorded |

## Phase 8: Training, Desktop Productization, Packaging, and Release Hardening

Detailed plan:

- `plans/2026-03-27-phase-8-desktop-productization-release.md`

Target outcome:

- Melix moves from an engineering runtime into a shippable local product with reproducible install, diagnostics, and release evidence

| Milestone | Focus | Main Outputs | Exit Gate |
| --- | --- | --- | --- |
| `P8-M1` | Native operator shell completion | richer dashboard, settings, logs, diagnostics, and remaining product-shell hydration | operator shell tests cover state hydration, actions, and reconnect behavior |
| `P8-M2` | Diagnostics, doctor, bench, and training | diagnostics pipeline, doctor commands, benchmark entrypoints, LoRA/QLoRA job entrypoints, failure triage surfaces | operator workflows can run diagnostics, bench, and training end-to-end |
| `P8-M3` | Adapter and training product tooling | adapter packaging, registry flows, training history, and backend-backed product controls | product tooling reads live training and adapter state rather than placeholders |
| `P8-M4` | Packaging and startup automation | launchd assets, installer/bootstrap scripts, signing and packaging structure, fresh-install flow | a clean machine can install and reach ready-state through scripted steps |
| `P8-M5` | Release gate automation | smoke gates, benchmark thresholds, restart recovery gates, training sanity gates, CI or release workflow integration | release candidates fail closed when smoke, benchmark, or training evidence is missing |
| `P8-M6` | Release runbooks and product acceptance | install, upgrade, rollback, diagnostics, training, and recovery runbooks plus final metrics report | cold boot, operator action latency, training duration, recovery success, and install metrics are all recorded |

## Cross-Phase Exit Rules

- Every milestone must end with touched-scope automated coverage at or above `95%`, or an explicit explanation plus the command needed to make coverage measurable.
- Every milestone must produce a metrics report for the changed hot path. `N/A` is valid only for documentation-only slices.
- Later-phase milestones must not start while earlier-phase worker or protocol dependencies remain placeholder logic.
- If a milestone expands a public API, it must also expand integration coverage and operator evidence in the same slice.
