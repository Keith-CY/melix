# Melix Full Capability Roadmap Execution Index

Parent roadmap: `docs/plans/2026-03-30-full-capability-roadmap.md`

This index maps every roadmap execution slice to its own implementation-plan document. Each child plan should be treated as an independent execution unit with its own verification and acceptance criteria.

The roadmap extension in `M10-M17` includes milestone-level plans plus decomposed child-plan documents for execution slices that already have stable ownership boundaries.

## M1: Runtime Core

- `M1.1` `docs/plans/2026-03-30-m1-1-residency-manager-contracts.md`
- `M1.2` `docs/plans/2026-03-30-m1-2-control-plane-residency-truth.md`
- `M1.3` `docs/plans/2026-03-30-m1-3-worker-memory-and-cache-accounting.md`
- `M1.4` `docs/plans/2026-03-30-m1-4-ttl-lru-pin-aware-eviction.md`
- `M1.5` `docs/plans/2026-03-30-m1-5-process-memory-enforcement.md`
- `M1.6` `docs/plans/2026-03-30-m1-6-prefill-memory-guards.md`
- `M1.7` `docs/plans/2026-03-30-m1-7-enforcement-disable-and-initial-cache-blocks.md`
- `M1.8` `docs/plans/2026-03-30-m1-8-lora-adapter-cache-isolation.md`
- `M1.9` `docs/plans/2026-03-30-m1-9-desktop-residency-and-memory-ui.md`
- `M1.10` `docs/plans/2026-03-30-m1-10-runtime-core-integration-evidence.md`

## M2: Cache V2 And Scheduler

- `M2.1` `docs/plans/2026-03-30-m2-1-block-table-and-restore-protocols.md`
- `M2.2` `docs/plans/2026-03-30-m2-2-text-worker-paged-cache-ownership.md`
- `M2.3` `docs/plans/2026-03-30-m2-3-block-refcount-and-copy-on-write.md`
- `M2.4` `docs/plans/2026-03-30-m2-4-partial-prefix-walk-back.md`
- `M2.5` `docs/plans/2026-03-30-m2-5-boundary-safe-prefill-chunking.md`
- `M2.6` `docs/plans/2026-03-30-m2-6-hot-cold-cache-tiers.md`
- `M2.7` `docs/plans/2026-03-30-m2-7-rotating-and-hybrid-cache-abstractions.md`
- `M2.8` `docs/plans/2026-03-30-m2-8-continuous-batching-and-scheduler-affinity.md`
- `M2.9` `docs/plans/2026-03-30-m2-9-prefill-progress-and-cache-pressure-metrics.md`
- `M2.10` `docs/plans/2026-03-30-m2-10-vlm-cache-reuse.md`
- `M2.11` `docs/plans/2026-03-30-m2-11-cache-recovery-benchmarks.md`

## M3: API Compatibility, Reasoning, Structured Output, And Tool Calling

- `M3.1` `docs/plans/2026-03-30-m3-1-shared-text-semantic-model.md`
- `M3.2` `docs/plans/2026-03-30-m3-2-anthropic-compatible-fields-and-thinking-blocks.md`
- `M3.3` `docs/plans/2026-03-30-m3-3-adaptive-thinking.md`
- `M3.4` `docs/plans/2026-03-30-m3-4-harmony-protocol-compatibility.md`
- `M3.5` `docs/plans/2026-03-30-m3-5-json-mode-and-schema-validation.md`
- `M3.6` `docs/plans/2026-03-30-m3-6-tool-parser-registry.md`
- `M3.7` `docs/plans/2026-03-30-m3-7-xml-and-namespaced-tool-parsing.md`
- `M3.8` `docs/plans/2026-03-30-m3-8-chat-template-kwargs.md`
- `M3.9` `docs/plans/2026-03-30-m3-9-reasoning-budgets-and-overflow-closure.md`
- `M3.10` `docs/plans/2026-03-30-m3-10-partial-mode-and-assistant-prefill.md`
- `M3.11` `docs/plans/2026-03-30-m3-11-streaming-completion-and-usage.md`
- `M3.12` `docs/plans/2026-03-30-m3-12-protocol-compatibility-test-matrix.md`

## M4: Vision, OCR, And Multimodal

- `M4.1` `docs/plans/2026-03-30-m4-1-native-vlm-runtime-lifecycle.md`
- `M4.2` `docs/plans/2026-03-30-m4-2-remote-and-local-image-ingress.md`
- `M4.3` `docs/plans/2026-03-30-m4-3-image-hash-cache-identity.md`
- `M4.4` `docs/plans/2026-03-30-m4-4-multi-image-request-semantics.md`
- `M4.5` `docs/plans/2026-03-30-m4-5-image-only-requests.md`
- `M4.6` `docs/plans/2026-03-30-m4-6-vlm-tool-parser-integration.md`
- `M4.7` `docs/plans/2026-03-30-m4-7-ocr-prompting-and-sampling-profiles.md`
- `M4.8` `docs/plans/2026-03-30-m4-8-vision-model-family-adapters.md`
- `M4.9` `docs/plans/2026-03-30-m4-9-vision-integration-evidence.md`

## M5: Embedding, Reranker, And Model-Family Expansion

- `M5.1` `docs/plans/2026-03-30-m5-1-bert-and-xlmr-embedding-backends.md`
- `M5.2` `docs/plans/2026-03-30-m5-2-bge-and-mxbai-family-support.md`
- `M5.3` `docs/plans/2026-03-30-m5-3-jina-v3-reranker.md`
- `M5.4` `docs/plans/2026-03-30-m5-4-causal-lm-reranker-scoring.md`
- `M5.5` `docs/plans/2026-03-30-m5-5-architecture-detection-and-directory-inference.md`
- `M5.6` `docs/plans/2026-03-30-m5-6-model-family-capability-adapters.md`
- `M5.7` `docs/plans/2026-03-30-m5-7-family-integration-matrix.md`

## M6: Quantization And Inference Acceleration

- `M6.1` `docs/plans/2026-03-30-m6-1-oq-quantization-pipeline.md`
- `M6.2` `docs/plans/2026-03-30-m6-2-oq2-to-oq8-mixed-precision.md`
- `M6.3` `docs/plans/2026-03-30-m6-3-oq35-vlm-fp8-and-hybrid-quantization.md`
- `M6.4` `docs/plans/2026-03-30-m6-4-awq-and-sensitivity-planning.md`
- `M6.5` `docs/plans/2026-03-30-m6-5-oqe-gptq-and-hessian-compensation.md`
- `M6.6` `docs/plans/2026-03-30-m6-6-moe-and-dense-quantization-strategies.md`
- `M6.7` `docs/plans/2026-03-30-m6-7-kv-cache-quantization-acceleration.md`
- `M6.8` `docs/plans/2026-03-30-m6-8-sparse-prefill-acceleration.md`
- `M6.9` `docs/plans/2026-03-30-m6-9-quantization-conflict-locking.md`
- `M6.10` `docs/plans/2026-03-30-m6-10-huggingface-hub-upload-for-quantized-artifacts.md`
- `M6.11` `docs/plans/2026-03-30-m6-11-quantization-benchmark-and-regression-gates.md`

## M7: Benchmark And Evaluation Platform

- Status: completed. M7 closure landed under the active umbrella execution plan `docs/plans/2026-04-03-m7-lora-benchmark-cli-productization.md`; benchmark Window UI, CSV, and CLI productization continue as post-M7 work in the same transaction.

- `M7.1` `docs/plans/2026-03-30-m7-1-serving-benchmark-job-schema.md`
- `M7.2` `docs/plans/2026-03-30-m7-2-evaluation-suite-job-schema.md`
- `M7.3` `docs/plans/2026-03-30-m7-3-serving-benchmark-runners.md`
- `M7.4` `docs/plans/2026-03-30-m7-4-offline-dataset-packaging-and-runners.md`
- `M7.5` `docs/plans/2026-03-30-m7-5-evaluation-suite-coverage.md`
- `M7.6` `docs/plans/2026-03-30-m7-6-benchmark-queue-sample-size-and-batch-factors.md`
- `M7.7` `docs/plans/2026-03-30-m7-7-result-export-and-comparison-tables.md`
- `M7.8` `docs/plans/2026-03-30-m7-8-vlm-benchmark-options.md`
- `M7.9` `docs/plans/2026-03-30-m7-9-community-submission-and-device-identity.md`
- `M7.10` `docs/plans/2026-03-30-m7-10-benchmark-and-eval-release-gates.md`

## M8: Model Registry, Hub, Admin, And Platform Productization

- Status: completed. `M8.1-M8.11` are completed and verified under the repository execution plans,
  including the repository-owned Apple Silicon packaging target matrix and target-specific
  install/update metadata closure in `M8.11`.

- `M8.1` `docs/plans/2026-03-30-m8-1-multi-root-model-registry.md`
- `M8.2` `docs/plans/2026-03-30-m8-2-provider-org-model-variant-scanning.md`
- `M8.3` `docs/plans/2026-03-30-m8-3-huggingface-search-pagination-and-cards.md`
- `M8.4` `docs/plans/2026-03-30-m8-4-resumable-downloads-retries-and-mirrors.md`
- `M8.5` `docs/plans/2026-03-30-m8-5-admin-surface-expansion.md`
  Status: completed. The native operator shell now covers the runtime, models, downloads, training, diagnostics, logs, settings, chat, image, server, and API workflows through control-plane-backed menu bar surfaces, and repository-default Swift plus integration verification have been rerun to close the slice.
- `M8.6` `docs/plans/2026-03-30-m8-6-tab-persistence-and-offline-admin-assets.md`
  Status: completed. Operator-session persistence now restores the selected admin tool section, legacy payloads without `selected_tool_section` remain backward compatible, the repository-owned smoke command verifies secure state persistence, and the offline-owned admin-assets contract is documented in the runbook.
- `M8.7` `docs/plans/2026-03-30-m8-7-model-settings-completion.md`
  Status: completed. The native menu bar operator shell now exposes typed per-model settings for alias, type override, TTL, pin-on-load, adaptive thinking, parser fallback, and effective OCR/parser defaults, with repository-default verification and changed-line coverage evidence recorded in the repository.
- `M8.8` `docs/plans/2026-03-30-m8-8-generation-config-and-ocr-sampling-controls.md`
  Status: completed. Registry-discovered models now import `generation_config.json` defaults into inspectable metadata, request shaping consumes those defaults through a shared sampling policy with OCR-specific fallback precedence, and the native operator shell exposes OCR sampling controls plus generation-config provenance with repository-default verification and changed-line coverage evidence.
- `M8.9` `docs/plans/2026-03-30-m8-9-homebrew-formula-and-services.md`
  Status: completed. The repository now owns a Homebrew formula, a directly supervised `brew services` wrapper for the three-process Melix runtime bundle, deterministic formula/service smoke commands, and a dedicated runbook for install, upgrade, stop, and prune workflows.
- `M8.10` `docs/plans/2026-03-30-m8-10-auto-update-and-startup-failure-handling.md`
  Status: completed. Packaged installs now record product-version and update-channel metadata,
  requested-versus-selected HTTP-port diagnostics, authoritative ready-probe and log paths, and
  deterministic startup-failure classifications that the native operator shell projects into update
  state plus actionable startup guidance, with repository-default verification and changed-line
  coverage evidence recorded in the repository.
- `M8.11` `docs/plans/2026-03-30-m8-11-platform-packaging-and-target-differentiation.md`
  Status: completed. Melix now owns a shared packaging target matrix for
  `launch_agents_checkout`, `homebrew_service`, and `macos_app_bundle_preview`, with target
  metadata projected into the generated launch-agent install manifest, Homebrew service manifest,
  and preview app-bundle metadata plus deterministic smoke coverage and updated packaging runbooks.

## M9: Ecosystem, Agent Integrations, Security, And Stability Completion

- `M9.1` `docs/plans/2026-03-30-m9-1-mcp-tool-loading-and-auto-injection.md`
  Status: completed in commit `597ba91`.
- `M9.2` `docs/plans/2026-03-30-m9-2-agent-integration-exports.md`
  Status: completed in commit `3fd8ddb`.
- `M9.3` `docs/plans/2026-03-30-m9-3-additional-api-keys-and-shared-access.md`
  Status: completed. Shared-access policy, multi-key gateway enforcement, menu bar operator projection, runbook guidance, smoke coverage, and changed-line coverage evidence are recorded in the repository.
- `M9.4` `docs/plans/2026-03-30-m9-4-persistent-sessions-and-remember-me.md`
  Status: completed. Persistent auth-session storage, bootstrap restore, structured remember-me gateway routes, operator projection, runbook guidance, smoke coverage, and changed-line coverage evidence are recorded in the repository.
- `M9.5` `docs/plans/2026-03-30-m9-5-rich-output-sanitization.md`
  Status: completed. Shared sanitizer rules, gateway and operator enforcement coverage, runbook guidance, metrics assertions, and changed-line coverage evidence are recorded in the repository.
- `M9.6` `docs/plans/2026-03-30-m9-6-connection-lifecycle-hardening.md`
  Status: completed. Lifecycle policy loading, bounded disconnect grace, resumable chat streaming, repository-owned smoke and integration evidence, runbook guidance, and changed-line coverage evidence are recorded in the repository.
- `M9.7` `docs/plans/2026-03-30-m9-7-security-and-stability-closure-audit.md`
  Status: completed. Typed closure-audit findings, repository-owned JSON emission, runbook and decision guidance, phase-metrics exposure, and changed-line coverage evidence are recorded in the repository.
- `M9.8` `docs/plans/2026-03-30-m9-8-ecosystem-and-security-release-gates.md`
  Status: completed. The Phase 8 gate now consumes repository-owned M9 evidence, exposes `release_gate.m9_*` counters through the metrics pipeline, ships a deterministic `m9_release_gate_smoke.py` fixture command, and records changed-line coverage evidence for the touched Python scope.

## M10: Session Lifecycle And Power Management

- Status: completed. The repository now owns typed runtime-session lifecycle and idle-policy
  protocol state, control-plane lifecycle mutation surfaces, desktop operator banners and controls,
  plus live lifecycle smoke evidence and recovery runbook guidance.

- `M10.1` `docs/plans/2026-03-31-m10-1-session-state-protocol-and-snapshots.md`
  Status: completed. The control-plane protocol now exposes dedicated server-session runtime
  lifecycle and power-state snapshots, `server.state_changed` carries typed runtime-session
  payloads, the native menu bar client consumes the new payload directly, and repository-default
  Swift verification plus changed-line coverage evidence are recorded in the repository.
- `M10.2` `docs/plans/2026-03-31-m10-2-power-policy-and-lifecycle-controls.md`
  Status: completed. The control plane now exposes typed lifecycle and idle-policy mutations for
  server sessions, authoritative runtime-session idle transitions and aggregate server-state
  derivation are test-covered, the `melix` CLI can operate the lifecycle surface directly, and
  repository-default verification plus changed-line coverage evidence are recorded in the
  repository.
- `M10.3` `docs/plans/2026-03-31-m10-3-desktop-status-banners-and-operator-surfaces.md`
  Status: completed. The native desktop shell now projects control-plane-owned runtime-session
  lifecycle and idle-policy truth through lifecycle banners, inline chat notices, and
  session-scoped operator controls, with repository-default Swift verification and changed-line
  coverage evidence recorded in the repository.
- `M10.4` `docs/plans/2026-03-31-m10-4-session-lifecycle-integration-evidence.md`
  Status: completed. Melix now ships a repository-owned `melix-session-lifecycle-smoke`
  executable, live integration coverage against real worker processes, machine-readable lifecycle
  metrics, and an operator runbook for pause, idle sleep, wake, and restart recovery.

## M11: Disk Streaming, Memory Budgeting, And Cache Policy

- Status: completed. `M11.1` is completed with typed disk-streaming settings, worker-facing
  runtime flags, explicit unsupported-runtime failures, and operator-visible session or residency
  state. `M11.2` is completed with repository-owned memory-budget load settings, typed headroom
  rejection evidence, and operator-visible budget summaries. `M11.3` is completed with typed cache
  policy summaries, effective streaming-compatibility resolution, worker-aligned cache settings,
  and operator-visible requested-versus-effective cache state. `M11.4` is completed with a
  repository-owned `melix-disk-streaming-smoke` harness, live unsupported-path smoke coverage,
  machine-readable RAM-baseline benchmark evidence, and an operator runbook that documents the
  truthful current boundary where SSD-backed restore and throughput metrics remain unavailable.

- `M11.1` `docs/plans/2026-03-31-m11-1-disk-streaming-mode-and-runtime-flags.md`
  Status: completed. Disk-streaming mode is now part of the repository-owned control-plane and
  worker protocol, unsupported runtime paths fail with typed `disk_streaming_unsupported` errors,
  runtime-session and residency snapshots project requested versus effective disk-streaming mode,
  and the native operator shell exposes the mode through typed settings and server-session detail.
- `M11.2` `docs/plans/2026-03-31-m11-2-memory-budget-admission-and-safety-guards.md`
  Status: completed. The control-plane contract now carries per-load and per-model
  `memory_budget_bytes`, unsafe-load rejections project `budget`, `headroom`, and `required`
  evidence into residency summaries plus metrics, and the native desktop shell exposes the budget
  setting and rejection detail through model settings and summaries.
- `M11.3` `docs/plans/2026-03-31-m11-3-streaming-cache-compatibility-and-settings-surface.md`
  Status: completed. Cache mode, memory-budget, block-size, directory, and multimodal-cache
  controls now flow through the repository-owned control-plane contract, worker summaries, native
  operator settings, and effective cache-policy projection, with changed-line coverage and full
  repository verification recorded in the repository.
- `M11.4` `docs/plans/2026-03-31-m11-4-large-model-streaming-benchmarks-and-runbooks.md`
  Status: completed. Melix now ships a repository-owned `melix-disk-streaming-smoke`
  executable, focused Swift and live integration coverage, machine-readable RAM-baseline and
  unsupported-path disk-streaming evidence, and an operator runbook that explains the current
  truthful runtime boundary while preserving future SSD metrics as explicit placeholders.

## M12: Model Registry, Family Coverage, And Model Tools

- `M12.1` `docs/plans/2026-03-31-m12-1-multi-root-registry-management-and-rescan.md`
  Status: completed. Multi-root registry configuration is now control-plane-owned, worker-backed,
  and operator-visible across stable root identity, ordered rescans, explicit empty-root
  overrides, and Window UI root-management actions, with focused verification and changed-line
  coverage evidence recorded in the repository.
- `M12.2` `docs/plans/2026-03-31-m12-2-text-and-moe-family-adapters.md`
  Status: completed. Dense and MoE text-family adapters now project family-specific routing,
  parser, attention, RoPE, and MoE declarations through worker registry snapshots, control-plane
  catalog sync, the repository-owned support matrix, and deterministic live-path integration
  coverage.
- `M12.3` `docs/plans/2026-03-31-m12-3-image-family-dispatch-and-picker-completion.md`
  Status: completed. Supported creative image families now carry stable family identity,
  generate-versus-edit role declarations, and operator-visible picker metadata through worker
  registry snapshots, control-plane catalog sync, the repository-owned family support matrix, and
  focused live-path validation.
- `M12.4` `docs/plans/2026-03-31-m12-4-model-inspect-health-and-conversion-tools.md`
  Status: completed. Typed model inspection, structured doctor health, and model-tool conversion
  packaging are now repository-owned workflows with stable artifact schemas, upload receipts,
  runtime compatibility metadata, and Window UI summary state backed by focused changed-line
  coverage evidence.

## M13: Gateway Configuration, Defaults, And API Onboarding

- `M13.1` `docs/plans/2026-03-31-m13-1-gateway-config-state-model-and-persistence.md`
  Status: completed. Gateway listener configuration is now a typed, persistent, control-plane-owned
  contract with bootstrap-backed precedence resolution, snapshot projection, typed desktop apply
  actions, and focused changed-line coverage across control-plane and Window UI surfaces.
- `M13.2` `docs/plans/2026-03-31-m13-2-generation-batching-and-speculative-defaults.md`
  Status: completed. Generation, batching, and speculative-decoding defaults are now typed,
  persistent, and operator-visible through the control-plane serving-defaults path, with explicit
  validation for unsupported speculative targets, requested-versus-effective projection in the
  desktop shell, isolated integration startup state, and focused changed-line coverage evidence
  across Swift and Python helper scopes.
- `M13.3` `docs/plans/2026-03-31-m13-3-tooling-embedding-and-config-file-settings.md`
- `M13.4` `docs/plans/2026-03-31-m13-4-api-reference-and-quick-start-onboarding.md`
  Status: completed. The desktop API workspace now projects supported endpoint reference and
  session-aware quick-start snippets from typed control-plane onboarding truth, and the canonical
  `/health`, `/v1/responses`, and `/v1/messages` examples are exercised by a repository-owned live
  smoke plus focused integration coverage so the onboarding material stays aligned with shipped
  streaming behavior.

## M14: Image Iteration And Persisted Creative Workflows

- `M14.1` `docs/plans/2026-03-31-m14-1-image-variation-and-iterate-request-semantics.md`
  Status: completed. Image edit requests now carry typed `edit`, `variation`, and `iterate`
  modes, control-plane and OpenAI image edits can resolve prior artifacts by stable
  `source_artifact_id`, and worker plus control-plane image job records preserve parent-artifact,
  parent-job, and `prompt_delta` lineage for downstream desktop consumers.
- `M14.2` `docs/plans/2026-03-31-m14-2-persisted-image-defaults-and-role-aware-picker.md`
  Status: completed. Creative defaults are now persisted through a control-plane-owned image
  defaults store, projected as requested-versus-effective snapshot truth, and applied through
  capability-driven generate or edit model pickers plus typed Window UI request forwarding.
- `M14.3` `docs/plans/2026-03-31-m14-3-redo-actions-and-long-running-timeout-policy.md`
  Status: completed. Image jobs now preserve stable recipe and timeout-policy projection, creative
  image requests use typed long-running `deadline_exceeded` handling instead of generic worker
  unavailability, and the Window UI exposes redo or reiteration actions plus timeout-aware status
  text from control-plane-owned truth.
- `M14.4` `docs/plans/2026-03-31-m14-4-image-iteration-integration-and-artifact-lineage-evidence.md`
  Status: completed. The shipped HTTP image payload now exposes lineage and redo-inspection fields,
  live integration coverage proves variation, iterate, and redo reconstruction from repository
  artifacts, and `make phase7-metrics` plus the image operator runbook provide reproducible timeout,
  lineage, queueing, and cancelation evidence for the completed `M14` workflow family.

## M15: Desktop Signals, Download Recovery, And Streaming Polish

- `M15.1` `docs/plans/2026-03-31-m15-1-token-stream-presentation-smoothing.md`
  Status: completed. The desktop shell now smooths bursty assistant, reasoning, and tool deltas
  through a menubar-owned presentation queue, records UI-side chat presentation lag and flush-count
  metrics, and keeps exact transcript fidelity through terminal flush handling plus focused
  coverage-enabled menu-bar tests.
- `M15.2` `docs/plans/2026-03-31-m15-2-update-banners-and-runtime-signal-unification.md`
  Status: completed. Update availability and update-check-failure notices now participate in one
  shared desktop signal model with stable dismiss ids, persisted dismissal policy, and unified
  workspace-banner plus status-menu rendering, while critical runtime recovery signals remain
  non-dismissible and higher priority.
- `M15.3` `docs/plans/2026-03-31-m15-3-download-queue-persistence-and-paused-recovery.md`
  Status: completed. Download queue rows now persist through operator-session restore, the worker
  registry snapshot exposes `output_dir` plus `resume_ready` metadata for partial downloads, and
  the Window UI and status menu now surface shared recovery signals with queue-aware resume
  actions.
- `M15.4` `docs/plans/2026-03-31-m15-4-desktop-polish-integration-evidence.md`
  Status: completed. The repository now ships a desktop-polish smoke command, focused Swift smoke
  coverage, Python-side script plus integration validation, and a dedicated runbook that proves
  token smoothing, shared banner priority, persisted download recovery, and real navigation
  grounding across all desktop surfaces and tool sections.

## M16: Video Understanding And Media Lifecycle

- Status: completed. `M16.1-M16.4` are completed with explicit video ingress contracts,
  frame-policy routing, temporary-media lifecycle control, and repository-owned video smoke plus
  runbook evidence for local-path, remote-URL, bounded-window, cleanup, and routing-under-load
  scenarios.

- `M16.1` `docs/plans/2026-03-31-m16-1-video-ingress-and-media-normalization-contracts.md`
  Status: completed. The worker protocol now carries explicit video message parts and
  preprocessing metadata, Swift request normalization accepts supported URI and inline video
  forms with typed validation, and the Python worker now has a repository-owned video
  preprocessing contract helper with focused Swift plus Python coverage.
- `M16.2` `docs/plans/2026-03-31-m16-2-frame-policy-video-runtime-and-background-lane-routing.md`
  Status: completed. Video-bearing VLM requests now normalize into one effective request shape
  with explicit frame-policy state, background-lane routing remains authoritative through the Swift
  request coordinator, worker runtime probes export video frame and clip-window evidence, and the
  touched Python plus Swift scope records repository-owned changed-line coverage evidence.
- `M16.3` `docs/plans/2026-03-31-m16-3-temporary-media-lifecycle-cleanup-and-failure-recovery.md`
  Status: completed. Temporary multimodal analysis assets now flow through one repository-owned
  temp-media lifecycle helper, deterministic and MLX VLM runtimes report cleanup counts, bytes,
  latency, and failures through runtime stats, the Swift control plane publishes cleanup metrics
  for OCR and VLM routes, and focused Python, Swift, and integration coverage evidence is recorded
  in the repository.
- `M16.4` `docs/plans/2026-03-31-m16-4-video-integration-benchmarks-and-operator-evidence.md`
  Status: completed. The repository now ships a live-path video runtime smoke workflow, a
  machine-readable video operator-evidence metrics report, focused acceptance-metrics plus
  integration coverage, and a dedicated runbook for reproducing and diagnosing the current video
  path.

## M17: Speech Backends And Voice Catalog

- `M17.1` `docs/plans/2026-03-31-m17-1-speech-to-text-backend-adapters-and-model-matrix.md`
  Status: completed. The Swift control-plane catalog, Python bridge model-spec path, and
  repository-owned family support matrix now expose `Whisper`-class and `Parakeet`-class
  speech-to-text families with stable capability metadata and focused Swift, Python, and
  integration evidence.
- `M17.2` `docs/plans/2026-03-31-m17-2-text-to-speech-backend-adapters-and-multilingual-voice-catalog.md`
  Status: completed. The Swift control-plane catalog, Swift Python-bridge model-spec path,
  repository-owned family support matrix, and macOS operator model-info surface now expose
  `Kokoro`-class plus `Qwen3-TTS`-class speech families with stable voice-catalog, locale, voice
  mode, and install-profile metadata backed by focused Swift, Python, menubar, and integration
  evidence.
- `M17.3` `docs/plans/2026-03-31-m17-3-speech-settings-locale-policy-and-optional-dependency-profiles.md`
- `M17.4` `docs/plans/2026-03-31-m17-4-speech-integration-benchmarks-runbooks-and-operator-evidence.md`
