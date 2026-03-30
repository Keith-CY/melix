# Melix Full Capability Roadmap

Date: 2026-03-30

## Summary

Melix has completed the initial runtime, cache, multimodal, image, desktop, and release-acceptance phases needed for a local-first baseline. The next stage is not a single feature slice. It is a coordinated platform roadmap that expands Melix into a full local inference system with deeper runtime behavior, broader protocol compatibility, richer multimodal support, stronger quantization and evaluation workflows, and a more complete product surface for operators and external tools.

This roadmap is intentionally runtime-first. Each milestone should be delivered as a sequence of small `Mx.y` slices that are independently testable, independently reviewable, and independently measurable. Deterministic contract paths remain valid integration harnesses, but they do not count as completion for runtime-depth milestones that require real execution behavior.

The roadmap now also includes milestone-level product-completion extensions in `M10-M15`. These extension milestones stay aligned with the same control-plane-first architecture, but they are tracked as integrated execution-plan documents until they need finer-grained decomposition.

Execution-plan index: `docs/plans/2026-03-30-full-capability-roadmap-execution-index.md`

## Roadmap Principles

- Strengthen runtime depth before broadening product surfaces.
- Treat cache, memory, recovery, and scheduling as first-class platform capabilities.
- Keep protocol compatibility aligned across public APIs without fragmenting the internal execution model.
- Require restart and recovery evidence, not only single-request happy-path evidence.
- Require metrics and integration evidence for every milestone before it is considered complete.
- Keep experimental acceleration features behind explicit feature flags until benchmark evidence is stable.

## M10-M15 Coverage Map

The roadmap extension from `M10` through `M15` covers the following operator-visible and runtime-visible capability groups:

- Sessionized local serving and power-state management:
  explicit `loading`, `ready`, `paused`, `sleeping`, and `stopped` states; start, pause, resume, stop, and auto-sleep flows; light-sleep and deep-sleep thresholds; status banners in chat and admin surfaces.
- Disk streaming, memory budgeting, and cache policy:
  session-level disk streaming mode; virtual-memory budgeting; cache-compatibility policy under disk streaming; observable prefix-cache, paged-KV-cache, and persistent-disk-cache behavior; cache-memory limits, cache-memory percentage, block size, cache directories, and KV-cache quantization policy for large-model paths.
- Model registry, family coverage, and model tools:
  multiple model roots; ordered root scanning; structured identity; expanded text, MoE, and image-family coverage including `Mistral Small 4 (119B)`, `model_type: mistral4`, MLA attention, `128-expert MoE`, `YaRN interleaved RoPE`, `Nemotron-H`, MoE gate dequant, `Klein 4B/9B`, `Kontext`, `Fill`, `QwenImage`, and `FIBO`; model inspection; health checks; artifact conversion and quantized packaging workflows.
- Gateway configuration, defaults, and API onboarding:
  gateway config viewing and editing; served-model identity; host, port, API key, rate limit, timeout, log, and CORS settings; concurrent-processing, max-concurrent-sequence, prefill-batch-size, and completion-batch-size controls; batching and generation defaults; speculative-decoding controls; embedding-model selection; MCP and tool-parser settings; OpenAI, Anthropic, and Ollama onboarding material.
- Image iteration and persisted creative workflows:
  image variations; iterate and redo flows; explicit generate-versus-edit model roles; `30-minute` timeout policy; persisted image parameters for `steps`, `size`, `guidance`, `strength`, and `negative prompt`; picker coverage for `Kontext`, `Fill`, `QwenImage`, `FIBO`, and `Klein`.
- Desktop signals, download recovery, and streaming polish:
  smoother token rendering with typewriter presentation; update-availability banners; paused-download restoration after reopening the window; download-queue status improvements; status-bar clarity; product-shell placeholders that still remain grounded in real control-plane navigation.

## M1: Runtime Core

### Scope

- multi-model serving
- residency control
- eviction policy
- memory enforcement
- LoRA adapter cache isolation

### Target Outcome

Melix should serve text, embedding, rerank, and vision-family models concurrently while making residency, eviction, and memory protection explicit platform behavior rather than incidental worker-local behavior.

### Execution Slices

- `M1.1` Add shared residency-manager contracts for load, unload, pin, TTL, and eviction.
- `M1.2` Move residency truth into the control plane and remove scattered residency decisions.
- `M1.3` Extend worker runtime stats with resident, KV, and cache byte accounting.
- `M1.4` Implement `TTL + LRU + pin-aware` eviction semantics.
- `M1.5` Add process-level memory enforcement and model-load headroom checks.
- `M1.6` Add inline prefill memory guards and large-context protection.
- `M1.7` Add full-disable memory enforcement mode and configurable initial cache blocks.
- `M1.8` Add adapter-aware dispatch and cache namespace isolation for LoRA workflows.
- `M1.9` Surface residency, eviction, and memory-protection state in the desktop UI.
- `M1.10` Add live integration coverage for concurrent multi-model serving, adapter switching, LRU eviction, and memory guards.

### Exit Criteria

- At least one text, embedding, rerank, and vision-family model can be loaded and served concurrently.
- Eviction is not TTL-only and respects both pinning and recency.
- LoRA adapter switching does not incorrectly reuse cache from incompatible contexts.
- Memory guard failures are explicit, observable, and test-covered.

### Key Probes

- loaded-model count
- resident bytes per worker
- eviction count by reason
- prefill memory-guard trigger count
- model-load rejection count
- adapter-switch cache invalidation count

## M2: Cache V2 And Scheduler

### Scope

- paged KV cache
- per-block reuse
- copy-on-write
- SSD tiering
- continuous batching
- scheduler depth

### Target Outcome

Melix should upgrade from prefix-level hot cache plus snapshot persistence into a true paged-cache system with block-aware restore, continuous batching, and cache-affine scheduling.

### Execution Slices

- `M2.1` Define `BlockTable`, `PageRef`, `CacheRestorePlan`, and restore-boundary protocol shapes.
- `M2.2` Rebuild text-worker cache ownership around block and page primitives instead of only prefix records.
- `M2.3` Add per-block reference counting and copy-on-write semantics.
- `M2.4` Implement partial-prefix match and walk-back truncation.
- `M2.5` Implement boundary-safe prefill chunking.
- `M2.6` Add RAM hot tier and SSD cold tier with write-back mode.
- `M2.7` Add rotating and hybrid cache abstractions where needed for long-context paths.
- `M2.8` Upgrade the scheduler with continuous batching, cache affinity, and queue aging.
- `M2.9` Publish prefill progress, active and waiting request counts, restore-stage metrics, and cache-pressure metrics.
- `M2.10` Reuse the same cache abstraction for VLM requests.
- `M2.11` Add restart-reuse, partial-restore, and hot-cold tier recovery benchmarks.

### Exit Criteria

- The completed runtime path reports paged-cache support and continuous-batching support.
- Cache restore supports partial-prefix recovery and block-aware reuse.
- Recovery after restart is measurable by tier and restore stage.
- Continuous batching is active on the supported text path and observable in metrics.

### Key Probes

- cache block reuse ratio
- continuous-batch size and occupancy
- hot-tier and cold-tier hit rates
- restore latency by stage
- partial-prefix restore success rate
- walk-back truncation count

## M3: API Compatibility, Reasoning, Structured Output, And Tool Calling

### Scope

- OpenAI-compatible APIs
- Anthropic-compatible APIs
- Responses compatibility
- reasoning control
- structured outputs
- tool calling
- streaming completeness

### Target Outcome

Melix should expose a unified internal text semantic model while delivering compatible public API shapes for chat, completions, responses, and messages, with first-class reasoning and tool-calling behavior.

### Execution Slices

- `M3.1` Finish a single internal semantic model shared by chat, completions, responses, and messages.
- `M3.2` Complete Anthropic-compatible request and response fields, including thinking blocks and `x-api-key`.
- `M3.3` Add adaptive thinking support.
- `M3.4` Add harmony protocol compatibility.
- `M3.5` Implement `JSON mode` and `JSON Schema validation`.
- `M3.6` Add a parser registry for `JSON`, `Qwen`, `Gemma`, `MiniMax`, `GLM`, and `Mistral` tool-call formats.
- `M3.7` Add XML fallback parsing and namespaced tool-call parsing.
- `M3.8` Add `chat_template_kwargs` at per-model, per-request, and forced-override levels.
- `M3.9` Add reasoning budgets, reasoning-specific output fields, and forced think closure on overflow.
- `M3.10` Add partial mode, assistant prefill support, and name passthrough.
- `M3.11` Complete streaming behavior with `include_usage`, disconnect detection, SSE keepalive, and token-by-token tool-call streaming.
- `M3.12` Add protocol contract tests and SDK-compatibility smoke tests.
  - Repository-owned matrix location after landing:
    `services/control-plane-swift/Tests/HTTPGatewayTests/ProtocolCompatibilityMatrixTests.swift`
    and `tests/integration/test_protocol_compatibility_matrix.py`

### Exit Criteria

- All public text endpoints share one execution path and produce endpoint-appropriate protocol framing.
- Reasoning and tool-call data are available in both stream and completed outputs where applicable.
- Structured outputs and tool calling are validated, parsed, and observable.
- Disconnect and keepalive behavior are stable under long-running streams.

### Key Probes

- reasoning delta count
- tool-call parse success rate
- schema validation failure count
- stream disconnect detection latency
- keepalive cadence stability
- protocol-compatibility smoke pass rate

## M4: Vision, OCR, And Multimodal

### Scope

- native VLM runtime
- full image input support
- VLM plus tool calling
- OCR specialization
- broader vision-family support

### Target Outcome

Vision execution should become a real runtime path with proper batching, prefill, cache participation, and model-aware OCR behavior.

### Execution Slices

- `M4.1` Introduce a dedicated VLM runtime interface with explicit prefill and decode lifecycle.
- `M4.2` Add remote image fetch, local-path normalization, and image hashing.
- `M4.3` Include image hashes in cache and dedupe identity.
- `M4.4` Add multi-image request semantics end to end.
- `M4.5` Support image-only requests.
- `M4.6` Connect VLM tokenization to tool parser infrastructure.
- `M4.7` Add OCR auto-prompting, stop-token handling, and OCR-specific default sampling profiles.
- `M4.8` Add support adapters for broader vision-model families.
- `M4.9` Add live integration coverage for URL images, multi-image prompts, OCR defaults, and VLM tool calls.

### Exit Criteria

- VLM and OCR are no longer contract-only paths.
- Remote URLs, local files, inline payloads, multi-image requests, and image-only requests are all supported.
- Vision requests can participate in tool calling and cache reuse.
- OCR defaults are model-aware and test-covered.

### Key Probes

- image preprocess latency
- image fetch latency
- image hash dedupe hit rate
- VLM prefill latency
- OCR default-profile usage rate
- multi-image request pass rate

## M5: Embedding, Reranker, And Model-Family Expansion

### Scope

- native embedding backends
- native reranker families
- architecture detection
- expanded model-family support

### Target Outcome

Embedding and reranker support should move beyond the current basic path and support the requested model families through real family-specific backends.

### Execution Slices

- `M5.1` Add native `BERT` and `XLM-R` embedding backends.
- `M5.2` Add family adapters for `bge-m3` and `mxbai-embed` style models.
- `M5.3` Add `Jina v3` reranker scoring support.
- `M5.4` Add causal-LM reranker scoring, including yes-no logit scoring.
- `M5.5` Add architecture detection and directory-name inference.
- `M5.6` Add requested model-family support adapters and capability flags.
- `M5.7` Add a model-family integration matrix with live-path verification.

### Exit Criteria

- Embedding and rerank paths support real family-specific backends.
- Model-family selection and routing are not hardcoded to only seeded development models.
- Family-specific loading and scoring semantics are integration-tested.

### Key Probes

- embedding request latency by family
- rerank scoring latency by family
- architecture auto-detection success rate
- family-specific model load success rate

## M6: Quantization And Inference Acceleration

### Scope

- dynamic quantization
- enhanced quantization
- KV-cache acceleration
- experimental prefill acceleration

### Target Outcome

Quantization should become a real model-production subsystem, and acceleration features should become explicit runtime capabilities with feature flags and benchmark evidence.

### Execution Slices

- `M6.1` Define the `oQ` quantization pipeline and profile schema.
- `M6.2` Implement `oQ2-oQ8` with calibration-driven mixed-precision allocation.
- `M6.3` Add `oQ3.5`, VLM quantization, FP8-source handling, and hybrid quantization modes.
- `M6.4` Add AWQ-style equalization and sensitivity planning.
- `M6.5` Add `oQe` plus GPTQ and Hessian-based compensation.
- `M6.6` Split quantization strategies for MoE and dense families.
- `M6.7` Add KV-cache quantization acceleration behind a feature flag.
- `M6.8` Add sparse prefill acceleration behind a feature flag.
- `M6.9` Add quantization conflict locking so quantize jobs do not race active inference.
- `M6.10` Add direct HuggingFace Hub upload for produced artifacts.
- `M6.11` Add benchmark and regression gates for quantized artifacts.

### Exit Criteria

- Quantize jobs produce real runnable artifacts.
- Advanced quantization modes are represented in manifests, metrics, and compatibility checks.
- Experimental acceleration modes are benchmarked and revertible.
- Quantization and serving workflows are concurrency-safe.

### Key Probes

- quantization duration
- quantized artifact footprint
- post-quant benchmark delta
- quantization conflict-block count
- acceleration gain percentage
- regression-gate failure count

## M7: Benchmark And Evaluation Platform

### Scope

- built-in serving benchmark
- accuracy and intelligence evaluation
- result persistence
- comparison and export
- community submission

### Target Outcome

Melix should support both serving benchmarks and offline evaluation suites as first-class product capabilities, with persistent, comparable, and exportable results.

### Execution Slices

- `M7.1` Define serving-benchmark job and result schema.
- `M7.2` Define evaluation-suite job and result schema.
- `M7.3` Add built-in serving benchmark runners for prefill and generation throughput.
- `M7.4` Add offline dataset packaging and evaluation runners.
- `M7.5` Add the requested evaluation suites.
- `M7.6` Add benchmark queueing, sample-size selection, and batch-factor selection.
- `M7.7` Add raw JSON export and comparison tables.
- `M7.8` Add VLM benchmark options.
- `M7.9` Add community result submission and device-ID linkage.
- `M7.10` Feed benchmark and evaluation outputs into release gates.

### Exit Criteria

- Serving benchmarks and evaluation suites both run as productized jobs.
- Results persist across sessions and can be exported and compared.
- Release gates can consume benchmark and evaluation evidence.
- Community submission flow is defined and test-covered.

### Key Probes

- benchmark queue latency
- eval completion rate
- raw-result export count
- comparison-table generation time
- submission success rate

## M8: Model Registry, Hub, Admin, And Platform Productization

### Scope

- multi-root model registry
- Hub workflows
- admin completeness
- packaging and install
- platform controls

### Target Outcome

Melix should move from environment-variable-driven model paths to a real multi-root registry and a productized operator surface for discovery, download, configuration, installation, and update.

### Execution Slices

- `M8.1` Implement ordered multi-root model registry with sidecar manifests.
- `M8.2` Add `provider/org/model/variant` scanning, indexing, and reload.
- `M8.3` Add HuggingFace search, pagination, model-card inspection, and MLX-only filtering.
- `M8.4` Add resumable downloads, retries, stall detection, and mirror endpoint support.
- `M8.5` Expand the dashboard across runtime, models, chat, benchmark, tooling, and logs.
- `M8.6` Add tab persistence, URL state, and offline-vendored admin assets where applicable.
- `M8.7` Complete model settings for aliasing, type override, VLM fallback, direct-GB input, and sampling-config merge.
- `M8.8` Add `generation_config` import and OCR-specific sampling controls.
- `M8.9` Add Homebrew formula and `brew services`.
- `M8.10` Add auto-update, crash and hang detection, startup failure dialogs, and host-port management.
- `M8.11` Add platform-specific packaging and Apple Silicon target differentiation.

### Exit Criteria

- Model discovery is registry-driven rather than environment-variable-driven.
- Hub workflows are searchable, resumable, and operator-visible.
- Admin surfaces cover runtime, models, benchmark, chat, tooling, and logs.
- Install and update flows are productized and test-covered.

### Key Probes

- registry reload latency
- model discovery count by root
- download resume success rate
- dashboard tab-load latency
- startup failure classification count
- update-check success rate

## M9: Ecosystem, Agent Integrations, Security, And Stability Completion

### Scope

- MCP integration
- external coding-agent integrations
- shared access
- session security
- output sanitization
- connection lifecycle hardening

### Target Outcome

Melix should become a stable local runtime that external agentic tools can consume, while closing the remaining functional security and stability gaps.

### Execution Slices

- `M9.1` Add MCP configuration loading and tool auto-injection.
- `M9.2` Add export and integration paths for `OpenClaw`, `Hermes Agent`, `OpenCode`, `Codex`, and related external coding tools.
- `M9.3` Add additional API-key support and shared-access support.
- `M9.4` Add persistent session support and remember-me behavior.
- `M9.5` Add output sanitization for rendered rich text and HTML-capable surfaces.
- `M9.6` Harden connection lifecycle management with disconnect, retry, resume, and keepalive policy.
- `M9.7` Run a final security and stability closure audit.
- `M9.8` Add these capabilities to release gates.

### Exit Criteria

- External tooling can discover and consume Melix capabilities through supported integration paths.
- Shared-access and persistent-session behavior are stable and test-covered.
- Output sanitization is enforced on relevant rich-text surfaces.
- Connection lifecycle behavior is observable, recoverable, and measurable.

### Key Probes

- MCP tool-injection success rate
- external integration setup success rate
- persistent-session restore success rate
- disconnect recovery latency
- sanitized-output enforcement count

## M10: Session Lifecycle And Power Management

### Scope

- explicit server-session lifecycle
- power-state policy
- auto-sleep thresholds
- operator-visible session state
- lifecycle-safe resume and wake flows

### Target Outcome

Melix should treat local serving as an explicit session lifecycle rather than a binary process-up or process-down state, with clear pause, sleep, stop, and wake semantics across the control plane, APIs, and desktop shell.

### Execution Slices

- `M10.1` Define session-state protocol, snapshot, and event-model changes.
- `M10.2` Implement power policy, idle timers, and lifecycle controls in the control plane.
- `M10.3` Surface status banners and power-state controls in desktop operator flows.
- `M10.4` Add lifecycle integration coverage, smoke paths, and metrics evidence.

### Coverage

- explicit `loading`, `ready`, `paused`, `sleeping`, and `stopped` session states
- `start`, `pause`, `resume`, and `stop` controls
- configurable `auto_sleep`, `light_sleep_after`, and `deep_sleep_after` policy
- power-management state in chat, settings, and operator surfaces
- session-state banners for `loading`, `sleeping`, and `stopped`
- wake reasons, idle timers, and safe recovery from sleeping state

### Exit Criteria

- Session lifecycle transitions are explicit, measurable, and test-covered.
- Sleeping, paused, and stopped states are not conflated in UI or control-plane state.
- The desktop shell and API surfaces agree on current session and power state.
- Idle-to-sleep and wake flows preserve cache and model-state integrity.

### Key Probes

- session start latency
- pause transition latency
- sleep transition latency
- wake-to-ready latency
- session-state mismatch count
- auto-sleep trigger count

## M11: Disk Streaming, Memory Budgeting, And Cache Policy

### Scope

- disk streaming mode
- virtual-memory budgeting
- large-model safety policy
- cache compatibility under streaming
- observable SSD-backed execution costs

### Target Outcome

Melix should support controlled disk-backed execution for models that exceed practical RAM residency, while making memory budgets, cache tradeoffs, and operator-visible safety policy explicit.

### Execution Slices

- `M11.1` Add disk-streaming mode semantics and runtime-facing configuration.
- `M11.2` Add memory-budget admission, headroom checks, and safety guards.
- `M11.3` Expose streaming-compatible cache policy and settings surfaces.
- `M11.4` Add large-model streaming benchmarks, operator smoke paths, and runbooks.

### Coverage

- session-level disk streaming mode
- adjustable virtual-memory budget
- large-model load admission using memory and SSD budgets
- cache-disable or cache-limiting policy for incompatible streaming paths
- unified configuration for prefix cache, paged KV cache, persistent disk cache, cache memory limit, cache memory percentage, block size, block-cache directory, cache directory, max cache size, and cache quantization under this mode
- metrics for RAM pressure, SSD footprint, restore cost, and degraded-path latency

### Exit Criteria

- Disk-streaming mode can be enabled and observed without hidden side effects.
- Virtual-memory budgets gate unsafe loads before runtime instability.
- Cache policy under disk streaming is explicit and operator-visible.
- Recovery, warmup, and steady-state metrics distinguish RAM-resident and SSD-backed paths.

### Key Probes

- streamed-model load latency
- virtual-memory budget rejection count
- SSD-backed restore latency
- disk-streaming throughput delta
- cache-disable enforcement count
- SSD footprint by session

## M12: Model Registry, Family Coverage, And Model Tools

### Scope

- expanded model-family coverage
- ordered multi-root registry completion
- model inspection and health tooling
- artifact conversion and quantized packaging
- independent embedding-model selection

### Target Outcome

Melix should provide broad family-aware model support and a complete local model-operations surface, so operators can discover, validate, convert, and serve diverse text, MoE, embedding, and image models through one registry and tooling model.

### Execution Slices

- `M12.1` Complete multi-root registry management and operator-visible rescan behavior.
- `M12.2` Add text and MoE family adapters for expanded serving coverage.
- `M12.3` Add image-family dispatch and picker completion for supported creative families.
- `M12.4` Add inspect, health-check, and conversion tooling through stable model-ops paths.

### Coverage

- default plus user-added model roots with ordered scanning and reload
- structured provider, organization, model, and variant identity
- expanded text-family support for `Mistral Small 4 (119B)`, `model_type: mistral4`, MLA attention, `128-expert MoE`, `YaRN interleaved RoPE`, `Nemotron-H`, and MoE gate-dequant paths
- expanded image-family dispatch for `Klein 4B/9B`, `Kontext`, `Fill`, `QwenImage`, and `FIBO`, with correct class-based routing instead of pattern-only dispatch
- model inspection metadata, model health checks, and explicit failure reports
- HuggingFace-to-quantized-artifact workflow and independent embedding-model preload

### Exit Criteria

- Multi-root discovery and rescan are stable and operator-visible.
- Expanded family adapters can be loaded, routed, and verified through integration coverage.
- Model inspection and health tooling return coherent results through supported operator surfaces.
- Conversion and quantized packaging workflows are test-covered and tied to model metadata.

### Key Probes

- model scan latency by root
- family dispatch success rate
- health-check pass rate
- inspection request latency
- conversion job duration
- embedding-preload success rate

## M13: Gateway Configuration, Defaults, And API Onboarding

### Scope

- gateway configuration viewing and editing
- generation and batching defaults
- speculative-decoding and embedding-model controls
- API compatibility onboarding
- tool and MCP configuration visibility

### Target Outcome

Melix should expose a complete and inspectable local server configuration surface, with enough operator guidance that supported API consumers can connect without reading source code or guessing hidden defaults.

### Execution Slices

- `M13.1` Add a typed gateway-config state model and persistence flow.
- `M13.2` Add batching, generation-default, and speculative-decoding settings.
- `M13.3` Add embedding, tool-parser, MCP, config-file, and additional-arguments settings.
- `M13.4` Add API reference projection and quick-start onboarding material.

### Coverage

- host, port, API key, served-model name, rate-limit, timeout, log-level, and CORS settings
- concurrent-processing, max-concurrent-sequence, prefill-batch-size, and completion-batch-size controls
- default max tokens, default temperature, default top-p, and stream-interval defaults
- speculative-decoding controls, including draft-model selection and `num-draft-tokens` policy
- embedding-model selection, built-in tool-parser settings, MCP configuration, config-file path, and additional arguments
- OpenAI, Anthropic, and Ollama endpoint reference plus curl, Python, and JavaScript quick-start snippets

### Exit Criteria

- Gateway configuration is complete, operator-visible, and backed by control-plane truth.
- Default precedence between packaged defaults, config files, and operator overrides is explicit.
- API onboarding material matches live supported endpoints and payload expectations.
- Tool and MCP settings are visible without requiring direct file inspection.

### Key Probes

- gateway-config round-trip latency
- config-precedence conflict count
- onboarding example success rate
- endpoint reference generation latency
- speculative-config apply latency
- settings drift detection count

## M14: Image Iteration And Persisted Creative Workflows

### Scope

- image variations and iterate flows
- persisted image-generation defaults
- model-role separation for generation versus editing
- longer-running creative job policy
- image-family picker completion

### Target Outcome

Melix should turn image generation and editing into an iterative local workflow rather than a single-shot job API, while keeping long-running execution, timeout policy, and artifact lineage explicit.

### Execution Slices

- `M14.1` Add image-variation and iterate request semantics.
- `M14.2` Add persisted image defaults and role-aware model picking.
- `M14.3` Add redo actions and longer-running timeout policy.
- `M14.4` Add image-iteration integration coverage and artifact-lineage evidence.

### Coverage

- source-image variations with explicit strength control
- iterate-from-previous-artifact flow
- always-visible redo and reiteration actions
- explicit generate-model and edit-model role separation in the picker
- persisted defaults for steps, size, guidance, strength, and negative prompt
- longer `30-minute` timeout policy for generation and edit workflows, with operator-visible timeout state

### Exit Criteria

- Image iteration flows can reuse prior artifacts without bypassing image-job truth.
- Persisted image defaults survive restart and remain inspectable.
- Model-role distinctions are visible and validated in the picker and request paths.
- Longer-running image jobs have explicit timeout, cancel, and retry behavior.

### Key Probes

- variation request latency
- iterate action latency
- persisted-image-settings restore success rate
- timeout-trigger count
- image-role mismatch rejection count
- redo action usage count

## M15: Desktop Signals, Download Recovery, And Streaming Polish

### Scope

- smoother token rendering
- update and status messaging
- paused-download restoration
- queue and status-bar clarity
- grounded product-shell placeholders

### Target Outcome

Melix should finish the operator-facing desktop shell with clearer state signals, more polished streaming presentation, and stronger recovery behavior for long-running and interrupted product workflows.

### Execution Slices

- `M15.1` Add smooth token-stream presentation in the desktop shell.
- `M15.2` Unify update banners and runtime-signal messaging.
- `M15.3` Persist download queues and restore paused downloads after restart.
- `M15.4` Add desktop-polish integration coverage and navigation-grounding evidence.

### Coverage

- typewriter-style token rendering using a smooth UI-side presentation layer
- dismissible update-availability banner
- paused-download recovery after reopening the window
- richer download-queue and status-bar messaging
- session and runtime banners grounded in live control-plane state
- product-shell placeholders, including future-facing tabs, that remain attached to real navigation and control-plane truth

### Exit Criteria

- Token rendering polish does not distort or reorder streamed output.
- Paused downloads can be resumed after the desktop shell restarts.
- Update and runtime banners are dismissible, accurate, and test-covered.
- Queue and status messaging reduce operator ambiguity during long-running workflows.

### Key Probes

- token-render lag
- paused-download restore success rate
- banner dismissal persistence rate
- queue-status refresh latency
- desktop-state hydration mismatch count

## Execution Order

Execute in strict order:

`M1 -> M2 -> M3 -> M4 -> M5 -> M6 -> M7 -> M8 -> M9 -> M10 -> M11 -> M12 -> M13 -> M14 -> M15`

The only allowed forward exceptions are:

- urgent compatibility fixes from `M3`
- install or startup blockers from `M8`
- session-lifecycle or memory-safety blockers from `M10` and `M11`

Each milestone should later become its own dedicated execution-plan document before implementation begins.

## Verification Standard

Every milestone must add:

- protocol contract tests
- worker runtime unit tests
- control-plane integration tests
- desktop and operator workflow tests
- a metrics report for the touched scope

Every milestone exit gate must include:

- at least one live-path integration test
- at least one restart or recovery test
- at least one benchmark or metrics-improvement artifact
- touched-scope coverage of at least `95%`

Repository-wide verification baseline remains:

- `make proto`
- `make swift-test`
- `make py-test`
- `make integration-test`

## Assumptions

- Deterministic runtimes remain valid contract harnesses but do not count as completion for runtime-depth milestones.
- Experimental features such as advanced quantization and experimental acceleration may ship behind feature flags first, but they still require metrics, rollback paths, and release-gate awareness.
- The model-directory strategy is locked as `ordered multi-root + provider/org/model/variant + sidecar manifest`.
- Cache identity must include `adapter_set`, `parser_mode`, and `reasoning_profile` to prevent invalid reuse.
- `M10-M15` are product-completion milestones that intentionally combine operator-visible behavior with the runtime and control-plane hooks needed to support it.
- This document is the master roadmap. Each milestone must later be expanded into a separate execution plan with concrete implementation tasks.
