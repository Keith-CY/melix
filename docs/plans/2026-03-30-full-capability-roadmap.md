# Melix Full Capability Roadmap

Date: 2026-03-30

## Summary

Melix has completed the initial runtime, cache, multimodal, image, desktop, and release-acceptance phases needed for a local-first baseline. The next stage is not a single feature slice. It is a coordinated platform roadmap that expands Melix into a full local inference system with deeper runtime behavior, broader protocol compatibility, richer multimodal support, stronger quantization and evaluation workflows, and a more complete product surface for operators and external tools.

This roadmap is intentionally runtime-first. Each milestone should be delivered as a sequence of small `Mx.y` slices that are independently testable, independently reviewable, and independently measurable. Deterministic contract paths remain valid integration harnesses, but they do not count as completion for runtime-depth milestones that require real execution behavior.

Execution-plan index: `docs/plans/2026-03-30-full-capability-roadmap-execution-index.md`

## Roadmap Principles

- Strengthen runtime depth before broadening product surfaces.
- Treat cache, memory, recovery, and scheduling as first-class platform capabilities.
- Keep protocol compatibility aligned across public APIs without fragmenting the internal execution model.
- Require restart and recovery evidence, not only single-request happy-path evidence.
- Require metrics and integration evidence for every milestone before it is considered complete.
- Keep experimental acceleration features behind explicit feature flags until benchmark evidence is stable.

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

## Execution Order

Execute in strict order:

`M1 -> M2 -> M3 -> M4 -> M5 -> M6 -> M7 -> M8 -> M9`

The only allowed forward exceptions are:

- urgent compatibility fixes from `M3`
- install or startup blockers from `M8`

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
- This document is the master roadmap. Each milestone must later be expanded into a separate execution plan with concrete implementation tasks.
