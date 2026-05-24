# Issue 42 Multimodal Fast Paths Roadmap

## Source

- GitHub issue: <https://github.com/Keith-CY/melix/issues/42>
- Active planning branch: `codex/issue-42-multimodal-fast-paths`
- Original first-stage PR: #67

## Goal

Ship a Melix-owned multimodal fast-path layer around the pinned `mlx-vlm`
runtime so image, audio, and video-bearing requests are admitted through typed,
fail-closed contracts, produce auditable receipts, and can safely select faster
runtime paths without changing the public multimodal API.

The April 26 plan established the first admission and evidence layer:
supported VLM families report selected decode and quantized-load modes,
repeated images report feature-cache key reuse, and unsupported paths emit
explicit fallback receipts instead of silently looking optimized. Issue #42
comments after April 26 expand the same direction into four delivery milestones:
ingress/load receipts, runtime invariants, baseline fast paths, and gated
speculative acceleration.

## Current State

Implemented or partially implemented:

- Swift request normalization accepts typed image, audio, and video content
  parts and preserves source metadata in `MultimodalRequestNormalizer`.
- Worker-side VLM preprocessing prepares image and video requests, computes
  prompt and multimodal hashes, and records preprocessing probes.
- `MultimodalFastPathController` records conservative admission decisions for
  `baseline`, `single_stream`, `image_cache_reuse`, `native_quantized`, and
  `fallback` modes.
- VLM benchmark and phase-6 evidence reports expose image cache hit/miss
  counters and categorical fast-path metrics.
- Capability receipts exist in the control-plane model catalog, but they are not
  yet the full multimodal load/admission source of truth requested by the later
  Issue #42 comments.

Not yet proven:

- A shared request-level media-parts extractor used by chat, batch, diagnostics,
  and compatibility wrappers with per-turn media preservation and media-present
  fail-closed routing.
- Load receipts that reconcile config-declared modality, tensor evidence,
  processor contract, projector matching, optional heads, native draft support,
  and operator overrides before the first generation.
- Worker runtime receipts for `position_ids`, `rope_deltas`,
  `visual_pos_masks`, chunked prefill slices, quantized KV masks, hybrid-state
  patches, and cache-offset alignment.
- Real image-feature reuse. The current cache is a bounded feature-key receipt
  cache, not a reused image-encoder feature store.
- Image-bearing batch-1 step/direct decode. Image-bearing requests still use the
  pinned backend's streaming generation path.
- Media-bearing speculative decode. Current MTP speculative support is
  text-backed/prompt-only and explicitly rejects media inputs.

This PR is a narrow fail-closed unit for issue 42. It prioritizes correctness
and operator trust before generation: media-bearing chat requests must either be
admitted to a model that advertises the requested media modality, reject with a
typed 4xx response, or disable incompatible speculative defaults before worker
dispatch. This unit does not claim throughput or latency speedups.

## Public Interface Boundary

- Successful HTTP request and response shapes remain unchanged.
- No chat payload shape changes are required.
- Protobuf changes are allowed only when a receipt or diagnostic surface needs a
  typed field that cannot be represented safely through existing metadata.
- Unsupported multimodal admission paths return the existing OpenAI-style error
  envelope with typed Melix fields such as `reason`, `media_types`, and
  `model_id` so operators can distinguish capability, tool-routing, and
  acceleration refusals.
- Externally visible additions are limited to health/status payloads,
  diagnostics bundles, benchmark/evidence JSON, CLI status, and stable typed
  unsupported reasons.

## Design Principles

1. Admission is fail-closed. A loadable model is not automatically eligible for
   multimodal, native quantized, or speculative fast paths.
2. Public capability truth must match the effective route. If a checkpoint is
   served through text-only fallback, health and model metadata must withdraw
   unsupported media claims.
3. Typed media ingress happens once. Chat, batch, compatibility wrappers,
   diagnostics, and CLI paths consume the same normalized media-part summary.
4. Runtime speed follows correctness receipts. Position metadata, cache shape,
   chunking, quantized mask, and stream lifecycle invariants must be proved
   before a faster decode path can be promoted.
5. Speculative multimodal decode is gated and evidence-driven. Verification-only
   probes land before any default-on path.

## Target Metrics

Issue #42 success remains tied to measurable Apple Silicon evidence:

- At least `1.8x` single-stream multimodal decode throughput on the
  repository-owned smoke benchmark for supported baseline fast-path models.
- At least `50%` recovered image-encoder or media-preprocessing work for
  repeated-media conversations in the multimodal fixture set.
- No bridge/dequant fallback for supported native quantized multimodal loads in
  the acceptance matrix.
- No stale-position, mask-shape, cache-offset, text-only RoPE, or
  companion-state regressions in variable-length multimodal fixtures.
- No silent media drop. Unsupported media/model/tool/speculative combinations
  produce typed `4xx` responses or disabled reasons before decode.
- Gated speculative multimodal probes must show at least `1.25x` single-request
  decode improvement before promotion, and later at least `1.5x` for the
  supported smoke benchmark with no repeated-media correctness regression.

## Milestones

### Milestone 1: Typed Admission And Load Receipts

Build one fail-closed admission plane across request ingress, model activation,
health/status, diagnostics, and CLI. This milestone does not optimize decode; it
defines the truth that later fast paths consume.

Plans:

- Plan 1.1: Shared Media-Part Admission
- Plan 1.2: Multimodal Load Capability Receipts
- Plan 1.3: Operator-Visible Route And Cache Receipts

Exit gate:

- Chat, batch, compatibility, diagnostics, and direct CLI paths agree on typed
  media counts and per-turn association.
- Text-only, missing-processor, malformed-media, missing-tensor, stale-override,
  and unsupported tool/speculative combinations fail closed with typed reasons.
- `/health`, discovery/model metadata, CLI status, and diagnostics bundles expose
  the same effective route and unsupported reason vocabulary.

### Milestone 2: Runtime Position, Cache, And Prefill Invariants

Make the worker runtime prove the cache and position contracts that every fast
path depends on. This milestone still prioritizes fallback correctness over
throughput.

Plans:

- Plan 2.1: Position And Vision-Metadata Guards
- Plan 2.2: Chunked Prefill And Memory Admission
- Plan 2.3: Quantized KV, Hybrid-State, And Lifecycle Invariants

Exit gate:

- Variable-length image/video turns, text-only follow-ups through the multimodal
  path, and mixed-length batches cannot reuse stale vision metadata.
- Long media-expanded prefills choose a verified chunked path before Metal
  buffer or watchdog failures.
- Quantized KV masks, hybrid-state patches, and VLM stream teardown are covered
  by fixtures and diagnostics receipts.

### Milestone 3: Baseline Fast Paths And Native Quantized Loads

Replace admission-only receipts with real work avoidance for supported
families: actual media-feature reuse, batch-1 direct decode, and supported native
quantized multimodal loads.

Plans:

- Plan 3.1: Real Media Feature Cache Reuse
- Plan 3.2: Batch-1 Multimodal Decode Fast Path
- Plan 3.3: Native Quantized Multimodal Load Path

Exit gate:

- Repeated media fixtures prove at least `50%` recovered media work.
- Batch-1 multimodal decode overhead is within `5%` of the simple stream path or
  achieves the Issue #42 throughput target on the supported smoke benchmark.
- Supported quantized VLM fixtures stay on the native path across shard,
  sanitize, dtype, and optional-head cases.

### Milestone 4: Gated Speculative And Adaptive Multimodal Acceleration

Promote speculative/adaptive multimodal acceleration only after the prior
milestones produce load, route, cache, and position receipts that make it safe.

Plans:

- Plan 4.1: Verification-Only Draft/Verify Probes
- Plan 4.2: Native Draft Admission And Operator Overrides
- Plan 4.3: Performance Gate And Rollout Receipts

Exit gate:

- Verification-only probes preserve output parity and record acceptance,
  rollback, timing, and fallback receipts for media-bearing requests.
- Native draft/speculative activation is controlled by `auto`, `off`, and
  `force` policy with typed disabled reasons.
- Supported smoke probes meet the speculative speed target without increasing
  fallback or error rate.

## Executable Units

| Unit | Parent Plan | Summary |
|---|---|---|
| Unit 1.1.1 | Plan 1.1 | Add a shared normalized media-parts summary consumed by chat, batch, diagnostics, compatibility wrappers, and CLI paths. |
| Unit 1.1.2 | Plan 1.1 | Preserve per-turn media ordering and legacy top-level image fallback semantics with regression fixtures. |
| Unit 1.1.3 | Plan 1.1 | Fail closed for media-present requests on text-only runtimes, undecodable media, tool-incompatible media, and speculative-incompatible media. |
| Unit 1.2.1 | Plan 1.2 | Add tensor-index modality evidence for config-declared text, vision, audio, video, projector, and draft tensors. |
| Unit 1.2.2 | Plan 1.2 | Persist processor, projector, nested config, optional-head, and weight-remap load receipts before generation. |
| Unit 1.2.3 | Plan 1.2 | Add stale-setting and operator-override receipt coverage for native multimodal and native speculative admission. |
| Unit 1.3.1 | Plan 1.3 | Surface route, media count, cache count, unsupported reason, and fallback receipts through health, discovery, CLI, and diagnostics. |
| Unit 1.3.2 | Plan 1.3 | Add mixed image/audio/video and empty-media normalization matrix coverage for server-compatible and direct CLI requests. |
| Unit 1.3.3 | Plan 1.3 | Add packaged VLM audit fixtures proving bundled media routes, processor loading, and non-zero media-token expansion. |
| Unit 2.1.1 | Plan 2.1 | Record per-request position metadata receipts for `position_ids`, `rope_deltas`, media positions, and cache offsets. |
| Unit 2.1.2 | Plan 2.1 | Add shape guards for absent or stale vision metadata, image-free prefills, text-only follow-ups, and companion-state rederive. |
| Unit 2.1.3 | Plan 2.1 | Add mixed-length batch fixtures for per-row media geometry, prompt kwargs, left padding, and MRoPE delta overrides. |
| Unit 2.2.1 | Plan 2.2 | Add media-expanded attention-cost prediction and family-budgeted auto-chunk policy with opt-out. |
| Unit 2.2.2 | Plan 2.2 | Slice prompt-length-aware auxiliary tensors by `cache_offset + seq_len` in chunked prefills. |
| Unit 2.2.3 | Plan 2.2 | Add streaming and non-streaming preflight-budget parity fixtures for over-budget media prompts. |
| Unit 2.3.1 | Plan 2.3 | Add batched quantized KV mask fixtures with unequal offsets and unquantized-logit parity. |
| Unit 2.3.2 | Plan 2.3 | Add family-scoped hybrid-state patch/gate receipts for cache advance, contiguous state, and text-only RoPE. |
| Unit 2.3.3 | Plan 2.3 | Add VLM stream/cache lifecycle tests for unload, wake/resume, model switch, cache-hit replay, failure, and cancellation. |
| Unit 3.1.1 | Plan 3.1 | Replace feature-key-only receipts with a real media-feature cache for supported image-family preprocessing contracts. |
| Unit 3.1.2 | Plan 3.1 | Extend cache identity to typed audio/video media and prove repeated-media work recovery. |
| Unit 3.1.3 | Plan 3.1 | Persist cache hit/miss/work-saved counters consistently in CLI, server, benchmark, and diagnostics receipts. |
| Unit 3.2.1 | Plan 3.2 | Add image-bearing batch-1 direct/step decode admission behind receipt gates. |
| Unit 3.2.2 | Plan 3.2 | Thread executor-owned stream and integer token counters through the batch-1 multimodal decode loop. |
| Unit 3.2.3 | Plan 3.2 | Add performance probes comparing baseline and batch-1 fast path on the same prompt/model tuple. |
| Unit 3.3.1 | Plan 3.3 | Add cross-shard quantized metadata prepass before multimodal load and sanitize steps. |
| Unit 3.3.2 | Plan 3.3 | Preserve projector, vision tower, dtype, nested config, and optional-head tensors through native quantized loads. |
| Unit 3.3.3 | Plan 3.3 | Add native-vs-bridge acceptance fixtures and metrics for supported and unsupported quantized VLM artifacts. |
| Unit 4.1.1 | Plan 4.1 | Add verification-only media-bearing draft/verify probes behind a feature gate. |
| Unit 4.1.2 | Plan 4.1 | Record per-sequence accepted/rejected tokens, rounds, sampling parity, rollback, and fallback receipts. |
| Unit 4.1.3 | Plan 4.1 | Add single-request and concurrent speculative VLM parity fixtures. |
| Unit 4.2.1 | Plan 4.2 | Extend capability receipts for native draft heads, draft/target compatibility, adaptive block policy, and request gates. |
| Unit 4.2.2 | Plan 4.2 | Add operator overrides for multimodal route and native speculative mode with stale-setting suppression. |
| Unit 4.2.3 | Plan 4.2 | Render native acceleration receipts in health, CLI status, diagnostics, and benchmark artifacts. |
| Unit 4.3.1 | Plan 4.3 | Add baseline-vs-accelerated comparison artifacts for multimodal speculative decode. |
| Unit 4.3.2 | Plan 4.3 | Add Apple Silicon smoke probes for throughput, TTFT, acceptance rate, and fallback stability. |
| Unit 4.3.3 | Plan 4.3 | Add release/PR gate checks that block default-on promotion without speed, parity, and fallback evidence. |

## Issue Tracking Map

GitHub umbrella issues were created on 2026-05-23 and are listed below.

Milestone issues:

| Milestone | Issue |
|---|---:|
| Milestone 1: Typed Admission And Load Receipts | #1422 |
| Milestone 2: Runtime Position, Cache, And Prefill Invariants | #1423 |
| Milestone 3: Baseline Fast Paths And Native Quantized Loads | #1424 |
| Milestone 4: Gated Speculative And Adaptive Multimodal Acceleration | #1425 |

Plan issues:

| Plan | Parent Milestone | Issue |
|---|---|---:|
| Plan 1.1: Shared Media-Part Admission | #1422 | #1426 |
| Plan 1.2: Multimodal Load Capability Receipts | #1422 | #1427 |
| Plan 1.3: Operator-Visible Route And Cache Receipts | #1422 | #1428 |
| Plan 2.1: Position And Vision-Metadata Guards | #1423 | #1429 |
| Plan 2.2: Chunked Prefill And Memory Admission | #1423 | #1430 |
| Plan 2.3: Quantized KV, Hybrid-State, And Lifecycle Invariants | #1423 | #1431 |
| Plan 3.1: Real Media Feature Cache Reuse | #1424 | #1432 |
| Plan 3.2: Batch-1 Multimodal Decode Fast Path | #1424 | #1433 |
| Plan 3.3: Native Quantized Multimodal Load Path | #1424 | #1434 |
| Plan 4.1: Verification-Only Draft/Verify Probes | #1425 | #1435 |
| Plan 4.2: Native Draft Admission And Operator Overrides | #1425 | #1436 |
| Plan 4.3: Performance Gate And Rollout Receipts | #1425 | #1437 |

Executable unit issues:

| Unit | Parent Plan | Issue |
|---|---|---:|
| Unit 1.1.1: Shared normalized media-parts summary | #1426 | #1438 |
| Unit 1.1.2: Per-turn media ordering and legacy fallback | #1426 | #1439 |
| Unit 1.1.3: Media-present fail-closed request gates | #1426 | #1440 |
| Unit 1.2.1: Tensor-index modality evidence | #1427 | #1441 |
| Unit 1.2.2: Processor/projector/nested-config receipts | #1427 | #1442 |
| Unit 1.2.3: Stale settings and operator override receipts | #1427 | #1443 |
| Unit 1.3.1: Health/discovery/CLI/diagnostics route receipts | #1428 | #1444 |
| Unit 1.3.2: Mixed-media normalization matrix | #1428 | #1445 |
| Unit 1.3.3: Packaged VLM audit fixture | #1428 | #1446 |
| Unit 2.1.1: Position metadata receipts | #1429 | #1447 |
| Unit 2.1.2: Vision metadata shape guards | #1429 | #1448 |
| Unit 2.1.3: Mixed-length batch geometry fixtures | #1429 | #1449 |
| Unit 2.2.1: Attention-cost auto-chunk policy | #1430 | #1450 |
| Unit 2.2.2: Chunked auxiliary tensor slicing | #1430 | #1451 |
| Unit 2.2.3: Streaming budget parity fixtures | #1430 | #1452 |
| Unit 2.3.1: Batched quantized KV masks | #1431 | #1453 |
| Unit 2.3.2: Hybrid-state patch/gate receipts | #1431 | #1454 |
| Unit 2.3.3: VLM stream/cache lifecycle tests | #1431 | #1455 |
| Unit 3.1.1: Real image feature cache | #1432 | #1456 |
| Unit 3.1.2: Typed repeated audio/video cache identity | #1432 | #1457 |
| Unit 3.1.3: Work-saved cache counters | #1432 | #1458 |
| Unit 3.2.1: Image-bearing batch-1 decode admission | #1433 | #1459 |
| Unit 3.2.2: Executor stream and token-counter decode loop | #1433 | #1460 |
| Unit 3.2.3: Baseline-vs-fast-path probes | #1433 | #1461 |
| Unit 3.3.1: Cross-shard quantized metadata prepass | #1434 | #1462 |
| Unit 3.3.2: Native quantized tensor preservation | #1434 | #1463 |
| Unit 3.3.3: Native-vs-bridge quantized acceptance | #1434 | #1464 |
| Unit 4.1.1: Verification-only draft/verify probes | #1435 | #1465 |
| Unit 4.1.2: Speculative acceptance and rollback receipts | #1435 | #1466 |
| Unit 4.1.3: Speculative parity fixtures | #1435 | #1467 |
| Unit 4.2.1: Native draft capability receipts | #1436 | #1468 |
| Unit 4.2.2: Operator overrides and stale-setting suppression | #1436 | #1469 |
| Unit 4.2.3: Native acceleration status surfaces | #1436 | #1470 |
| Unit 4.3.1: Multimodal speculative comparison artifact | #1437 | #1471 |
| Unit 4.3.2: Apple Silicon speculative smoke probes | #1437 | #1472 |
| Unit 4.3.3: Promotion release/PR gates | #1437 | #1473 |

## Implementation Notes

- Unit 1.3.1 surfaces a shared public media-route receipt through HTTP discovery,
  `/api/capabilities`, `/v1/melix/health`, CLI discovery/model payloads,
  diagnostics debug bundles, and the menu bar decoders. The receipt exposes the
  effective route, declared and effective modalities, unsupported reason,
  request media-part and media-turn counts, and cache hit/miss counters. Public
  model metadata must use the effective modality list from this receipt instead
  of raw catalog declarations when a model is served by a text-only fallback.
- Unit 1.3.1 extends request normalization summary metadata with
  `melix.media_turn_count` so route receipts can distinguish total media parts
  from the number of user turns carrying media.
- Unit 1.3.2 adds an executable OpenAI chat normalization matrix for
  text+audio, text+image, image+audio, video+text, and empty-media payloads.
  The matrix proves server-compatible request bodies preserve ordered worker
  message parts, shared media-part summaries, and `melix.media_turn_count`.
  `melix chat run` still sends text-only `ControlPlaneChatRequest.Message`
  values, so there is no direct CLI media payload to compare in this unit.
- Unit 1.3.2 maps unsupported OpenAI multimodal `content[].type` values into
  `MultimodalRequestNormalizationError.unsupportedPartType` so HTTP ingress
  returns `unsupported_media_payload` with `unsupported_reason=
  unsupported_part_type` before model load or worker dispatch.
- Unit 1.3.2 keeps media-bearing OpenAI chat requests fail-closed when the
  selected model is absent from the catalog; admission returns
  `unsupported_media_for_model` with route kind `unknown` before lazy loading or
  worker dispatch.
- The fail-closed admission unit normalizes compatible media aliases, rejects
  media-bearing chat requests on text-only models before model load or
  generation, rejects media plus tools until multimodal tool routing is
  supported, and disables incompatible speculative defaults before VLM
  generation. It measures success with admission outcomes rather than speed:
  typed `4xx` responses for unsupported media requests, no worker
  load/generate call on rejected requests, and baseline acceleration metadata
  when speculative defaults are disabled for admitted media.
- Unit 1.3.3 extends the packaged VLM route receipt with
  `processor_modality_counts`, `media_token_expansion`,
  `packaged_media_route`, and `unsupported_reason`. The deterministic packaged
  cache smoke now audits a text+image prompt against the bundled MLX VLM route,
  records non-zero media-token expansion, and keeps Gemma4 processor/tokenizer
  load fixtures compatible when optional upstream hint parameters disappear.
- Unit 1.2.3 records serving-default override receipts with
  `melix.gateway_override_receipt.v1`. Launch-bound worker execution metadata and
  control-plane serving-default summaries expose suppressed override names,
  batch/speculative disabled reasons, route policies, effective route decisions,
  and cache-override omission reasons.
- Unit 1.2.3 summary receipts derive `effective_multimodal_route` from the
  active session default model metadata when route policy is not `off`, so VLM
  and OCR defaults report their Python multimodal routes instead of the Swift
  text fallback.
- Unit 1.2.3 treats incompatible saved batch settings as effective launch
  config, not raw requested config. `max_concurrent_requests`,
  `prefill_batch_size`, and `completion_batch_size` are suppressed when their
  requested values cannot produce a compatible batch capacity.
- Unit 1.2.3 route policy values are `auto`, `off`, and `force`.
  `multimodal_route_policy=force` fails closed until a native multimodal route
  exists for the active request path. Unsupported
  `speculative_route_policy=force` requests fail closed with
  `disabled_reason=unsupported_route`. `speculative_route_policy=off`
  preserves stale speculative operator input but launches with baseline
  speculative mode and `operator_disabled` receipt metadata.

## Verification Policy

Per milestone:

- Run focused Python and Swift tests for the touched scope.
- Run `git diff --check`.
- Run changed-scope coverage and report at least `95%`, or record an explicit
  `N/A` reason when the scope is not measurable.
- Include a metrics report. Documentation-only changes may use `N/A` with a
  reason; runtime or request-path changes must include probe output.

Full PR handoff still requires:

```bash
make proto
make swift-test
make py-test
make integration-test
```

Real speedup claims require matched baseline and accelerated artifacts for the
same model, prompt protocol, prompt digest, prompt template digest, task kind,
and generation config.
