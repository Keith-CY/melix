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

- Status: in progress. `M8.1-M8.6` are completed and verified under the repository execution plans; `M8.7-M8.11` remain pending productization slices.

- `M8.1` `docs/plans/2026-03-30-m8-1-multi-root-model-registry.md`
- `M8.2` `docs/plans/2026-03-30-m8-2-provider-org-model-variant-scanning.md`
- `M8.3` `docs/plans/2026-03-30-m8-3-huggingface-search-pagination-and-cards.md`
- `M8.4` `docs/plans/2026-03-30-m8-4-resumable-downloads-retries-and-mirrors.md`
- `M8.5` `docs/plans/2026-03-30-m8-5-admin-surface-expansion.md`
  Status: completed. The native operator shell now covers the runtime, models, downloads, training, diagnostics, logs, settings, chat, image, server, and API workflows through control-plane-backed menu bar surfaces, and repository-default Swift plus integration verification have been rerun to close the slice.
- `M8.6` `docs/plans/2026-03-30-m8-6-tab-persistence-and-offline-admin-assets.md`
  Status: completed. Operator-session persistence now restores the selected admin tool section, legacy payloads without `selected_tool_section` remain backward compatible, the repository-owned smoke command verifies secure state persistence, and the offline-owned admin-assets contract is documented in the runbook.
- `M8.7` `docs/plans/2026-03-30-m8-7-model-settings-completion.md`
- `M8.8` `docs/plans/2026-03-30-m8-8-generation-config-and-ocr-sampling-controls.md`
- `M8.9` `docs/plans/2026-03-30-m8-9-homebrew-formula-and-services.md`
- `M8.10` `docs/plans/2026-03-30-m8-10-auto-update-and-startup-failure-handling.md`
- `M8.11` `docs/plans/2026-03-30-m8-11-platform-packaging-and-target-differentiation.md`

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

- `M10.1` `docs/plans/2026-03-31-m10-1-session-state-protocol-and-snapshots.md`
- `M10.2` `docs/plans/2026-03-31-m10-2-power-policy-and-lifecycle-controls.md`
- `M10.3` `docs/plans/2026-03-31-m10-3-desktop-status-banners-and-operator-surfaces.md`
- `M10.4` `docs/plans/2026-03-31-m10-4-session-lifecycle-integration-evidence.md`

## M11: Disk Streaming, Memory Budgeting, And Cache Policy

- `M11.1` `docs/plans/2026-03-31-m11-1-disk-streaming-mode-and-runtime-flags.md`
- `M11.2` `docs/plans/2026-03-31-m11-2-memory-budget-admission-and-safety-guards.md`
- `M11.3` `docs/plans/2026-03-31-m11-3-streaming-cache-compatibility-and-settings-surface.md`
- `M11.4` `docs/plans/2026-03-31-m11-4-large-model-streaming-benchmarks-and-runbooks.md`

## M12: Model Registry, Family Coverage, And Model Tools

- `M12.1` `docs/plans/2026-03-31-m12-1-multi-root-registry-management-and-rescan.md`
- `M12.2` `docs/plans/2026-03-31-m12-2-text-and-moe-family-adapters.md`
- `M12.3` `docs/plans/2026-03-31-m12-3-image-family-dispatch-and-picker-completion.md`
- `M12.4` `docs/plans/2026-03-31-m12-4-model-inspect-health-and-conversion-tools.md`

## M13: Gateway Configuration, Defaults, And API Onboarding

- `M13.1` `docs/plans/2026-03-31-m13-1-gateway-config-state-model-and-persistence.md`
- `M13.2` `docs/plans/2026-03-31-m13-2-generation-batching-and-speculative-defaults.md`
- `M13.3` `docs/plans/2026-03-31-m13-3-tooling-embedding-and-config-file-settings.md`
- `M13.4` `docs/plans/2026-03-31-m13-4-api-reference-and-quick-start-onboarding.md`

## M14: Image Iteration And Persisted Creative Workflows

- `M14.1` `docs/plans/2026-03-31-m14-1-image-variation-and-iterate-request-semantics.md`
- `M14.2` `docs/plans/2026-03-31-m14-2-persisted-image-defaults-and-role-aware-picker.md`
- `M14.3` `docs/plans/2026-03-31-m14-3-redo-actions-and-long-running-timeout-policy.md`
- `M14.4` `docs/plans/2026-03-31-m14-4-image-iteration-integration-and-artifact-lineage-evidence.md`

## M15: Desktop Signals, Download Recovery, And Streaming Polish

- `M15.1` `docs/plans/2026-03-31-m15-1-token-stream-presentation-smoothing.md`
- `M15.2` `docs/plans/2026-03-31-m15-2-update-banners-and-runtime-signal-unification.md`
- `M15.3` `docs/plans/2026-03-31-m15-3-download-queue-persistence-and-paused-recovery.md`
- `M15.4` `docs/plans/2026-03-31-m15-4-desktop-polish-integration-evidence.md`

## M16: Video Understanding And Media Lifecycle

- `M16.1` `docs/plans/2026-03-31-m16-1-video-ingress-and-media-normalization-contracts.md`
- `M16.2` `docs/plans/2026-03-31-m16-2-frame-policy-video-runtime-and-background-lane-routing.md`
- `M16.3` `docs/plans/2026-03-31-m16-3-temporary-media-lifecycle-cleanup-and-failure-recovery.md`
- `M16.4` `docs/plans/2026-03-31-m16-4-video-integration-benchmarks-and-operator-evidence.md`

## M17: Speech Backends And Voice Catalog

- `M17.1` `docs/plans/2026-03-31-m17-1-speech-to-text-backend-adapters-and-model-matrix.md`
- `M17.2` `docs/plans/2026-03-31-m17-2-text-to-speech-backend-adapters-and-multilingual-voice-catalog.md`
- `M17.3` `docs/plans/2026-03-31-m17-3-speech-settings-locale-policy-and-optional-dependency-profiles.md`
- `M17.4` `docs/plans/2026-03-31-m17-4-speech-integration-benchmarks-runbooks-and-operator-evidence.md`
