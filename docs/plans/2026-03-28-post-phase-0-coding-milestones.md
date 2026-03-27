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

## Phase 2: Text Runtime Depth

Detailed plan:

- `plans/2026-03-27-phase-2-text-runtime-depth.md`

Target outcome:

- text execution becomes phase-aware, queue-aware, and observable rather than a single opaque `Generate` flow

| Milestone | Focus | Main Outputs | Exit Gate |
| --- | --- | --- | --- |
| `P2-M1` | Phase-aware protocol shapes | request lifecycle states, queue and admission metadata, `Prefill` and `Decode` message updates, control-plane event expansion | generated schemas compile and control-plane tests can represent queued, prefill, decode, and terminal phases |
| `P2-M2` | Scheduler lane read model | queue lanes, admission policy, priority hints, backpressure state, request progress snapshots | control-plane unit tests cover lane assignment and queue-state reporting |
| `P2-M3` | Prefill runtime | Swift worker `Prefill` implementation, prompt-processing checkpoints, prefill metrics probes | worker tests prove prefill can run and expose reusable intermediate state |
| `P2-M4` | Decode runtime | Swift worker `Decode` implementation, phased streaming continuation, decode throughput probes | resumed decode path streams tokens correctly from prefilled state |
| `P2-M5` | Abort and observability | abort across queued, prefill, and decode phases; richer request progress and scheduler metrics | integration tests cover cancellation from every lifecycle phase and report queue plus phase timings |
| `P2-M6` | Operator and benchmark evidence | local queue-pressure workflow, updated smoke scripts, phase-aware metrics report | admission latency, queue delay, TTFT, TPS, and abort latency are all measured and non-`N/A` |

## Phase 3: Cache, Session Graph, and Recovery

Detailed plan:

- `plans/2026-03-27-phase-3-cache-session-recovery.md`

Target outcome:

- reuse, branch-aware session state, and recovery move from planned abstractions into observable runtime behavior

| Milestone | Focus | Main Outputs | Exit Gate |
| --- | --- | --- | --- |
| `P3-M1` | Cache and session contracts | cache keys, block tables, snapshot refs, session graph and branch state in shared protocols | schema generation and control-plane models represent cache and branch metadata without placeholder gaps |
| `P3-M2` | Worker cache primitives | Swift worker cache metadata store, block table ownership, snapshot save and restore primitives | worker tests can persist and reload cache metadata for one model handle |
| `P3-M3` | Session graph state | control-plane session graph store, active branch tracking, resume metadata, branch lineage transitions | control-plane tests cover branch creation, selection, and resume metadata hydration |
| `P3-M4` | Recovery flows | checkpoint save policy, snapshot restore path, request resume semantics across tool boundaries | follow-up and restart-aware recovery paths pass integration tests |
| `P3-M5` | Cache-aware scheduling | prefix affinity, warm-route preference, reuse-aware admission decisions, cache pressure reporting | follow-up requests show measurable TTFT improvement versus cold baselines |
| `P3-M6` | Recovery evidence and operator path | restart smoke, cache inspection surface, recovery metrics report | hit rate, reuse ratio, restore latency, TTFT delta, and cache footprint are recorded |

## Phase 4: Text API Breadth and Agent Semantics

Detailed plan:

- `plans/2026-03-27-phase-4-text-api-breadth-agent-semantics.md`

Target outcome:

- Melix supports the next text endpoint family without diverging runtime semantics across clients

| Milestone | Focus | Main Outputs | Exit Gate |
| --- | --- | --- | --- |
| `P4-M1` | Endpoint contract alignment | request and response models for `/v1/responses` and `/v1/messages`, translation invariants, shared stream framing rules | protocol and translator tests define consistent cross-endpoint behavior |
| `P4-M2` | Responses endpoint | control-plane translator, HTTP handler, streaming support, endpoint-specific usage and finish mapping | `/v1/responses` passes unit and integration coverage with the existing text runtime |
| `P4-M3` | Messages endpoint | control-plane translator, handler, and state threading for `/v1/messages` | `/v1/messages` is live and test-covered without breaking chat completions or responses |
| `P4-M4` | Reasoning and tool deltas | normalized reasoning chunks, tool-call delta framing, endpoint-invariant event ordering | stream-fidelity tests validate reasoning and tool deltas across all text endpoints |
| `P4-M5` | Workflow-aware shaping | preset selection, workflow metadata, request normalization, session and branch continuity across endpoints | phase-specific request shaping behaves consistently for the same logical session |
| `P4-M6` | Endpoint evidence and metrics | endpoint-by-endpoint smoke, translation overhead report, stream latency report | translation latency and stream-fidelity metrics are recorded for chat, responses, and messages |

## Phase 5: Embeddings and Rerank

Detailed plan:

- `plans/2026-03-27-phase-5-embeddings-rerank.md`

Target outcome:

- the first non-generative worker classes land without eroding text responsiveness

| Milestone | Focus | Main Outputs | Exit Gate |
| --- | --- | --- | --- |
| `P5-M1` | Capability-class typing | capability metadata, model catalog typing, worker route classes, endpoint contracts for embeddings and rerank | catalog and protocol tests distinguish text, embeddings, and rerank routes cleanly |
| `P5-M2` | Embeddings runtime | Python embedding worker path, model load lifecycle, batch handling, throughput probes | worker tests and smoke requests produce stable embedding outputs |
| `P5-M3` | Rerank runtime | Python rerank path, scoring output model, candidate-window handling, latency probes | rerank worker tests cover scoring correctness and terminal error behavior |
| `P5-M4` | Control-plane endpoints and routing | `/v1/embeddings`, `/v1/rerank`, route selection, health and model visibility updates | both endpoints are live without changing the text hot path |
| `P5-M5` | Mixed-workload protection | worker isolation, queue policy for text vs retrieval workloads, memory-pressure reporting | text TTFT stays within target while embeddings and rerank traffic run concurrently |
| `P5-M6` | Integration and benchmark evidence | mixed-load integration suite, operator smoke, throughput and interference report | embeddings throughput, rerank latency, text interference, and memory metrics are recorded |

## Phase 6: Vision, OCR, and Audio Transcription

Detailed plan:

- `plans/2026-03-27-phase-6-vision-ocr-audio-transcription.md`

Target outcome:

- multimodal analysis capabilities arrive with dedicated preprocessing, routing, and isolation

| Milestone | Focus | Main Outputs | Exit Gate |
| --- | --- | --- | --- |
| `P6-M1` | Multimodal contracts | image and audio input normalization rules, capability typing, OCR/VLM/transcription protocol surfaces | protocol and request-normalization tests cover accepted multimodal payload shapes |
| `P6-M2` | OCR and VLM runtime | Python preprocessing adapters, OCR runtime, VLM inference path, memory probes | worker smoke covers OCR extraction and one image-to-text VLM path |
| `P6-M3` | Audio transcription runtime | audio preprocessing, transcription worker runtime, transcription response mapping | transcription tests cover file handling, chunking, and final transcript output |
| `P6-M4` | Control-plane routing and endpoint surface | multimodal route selection, `/v1/audio/transcriptions`, model visibility updates | transcription endpoint is live and multimodal analysis requests route correctly |
| `P6-M5` | Isolation and observability | background lanes for multimodal analysis, text-protection policy, preprocessing metrics and pressure reporting | text responsiveness remains stable under OCR/VLM/transcription traffic |
| `P6-M6` | Integration and operator workflows | multimodal dev smoke, runbooks, latency and memory report | OCR latency, transcription latency, VLM first-token latency, and preprocessing memory spikes are recorded |

## Phase 7: Image Generation and Image Editing

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
| `P7-M5` | Isolation and cancellation | background pool isolation, cancel path hardening, queue-pressure metrics | image traffic does not collapse text responsiveness and cancellation is reliable |
| `P7-M6` | Integration and operator evidence | artifact smoke tests, operator flows, latency and resource report | image latency, queue wait, cancel success, and peak resource metrics are recorded |

## Phase 8: Desktop Productization, Packaging, and Release Hardening

Detailed plan:

- `plans/2026-03-27-phase-8-desktop-productization-release.md`

Target outcome:

- Melix moves from an engineering runtime into a shippable local product with reproducible install, diagnostics, and release evidence

| Milestone | Focus | Main Outputs | Exit Gate |
| --- | --- | --- | --- |
| `P8-M1` | Native operator shell foundation | richer menu bar state model, dashboard hydration, settings shell, logs and status navigation | operator shell tests cover state hydration, actions, and reconnect behavior |
| `P8-M2` | Diagnostics, doctor, and bench | diagnostics pipeline, doctor commands, benchmark entrypoints, failure triage surfaces | operator workflows can run diagnostics and bench commands end-to-end |
| `P8-M3` | Backend-backed product tooling | cache inspector, presets, workflow controls, only where prior phases already expose the required state | product tooling reads live backend state rather than placeholder data |
| `P8-M4` | Packaging and startup automation | launchd assets, installer/bootstrap scripts, signing and packaging structure, fresh-install flow | a clean machine can install and reach ready-state through scripted steps |
| `P8-M5` | Release gate automation | smoke gates, benchmark thresholds, restart recovery gates, CI or release workflow integration | release candidates fail closed when smoke or benchmark evidence is missing |
| `P8-M6` | Release runbooks and product acceptance | install, upgrade, rollback, diagnostics, and recovery runbooks plus final metrics report | cold boot, operator action latency, recovery success, and install metrics are all recorded |

## Cross-Phase Exit Rules

- Every milestone must end with touched-scope automated coverage at or above `95%`, or an explicit explanation plus the command needed to make coverage measurable.
- Every milestone must produce a metrics report for the changed hot path. `N/A` is valid only for documentation-only slices.
- Later-phase milestones must not start while earlier-phase worker or protocol dependencies remain placeholder logic.
- If a milestone expands a public API, it must also expand integration coverage and operator evidence in the same slice.
