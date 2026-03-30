# Melix Full Capability Roadmap Execution Index

Parent roadmap: `docs/plans/2026-03-30-full-capability-roadmap.md`

This index maps every roadmap execution slice to its own implementation-plan document. Each child plan should be treated as an independent execution unit with its own verification and acceptance criteria.

The roadmap extension in `M10-M15` is currently tracked as one implementation-plan document per milestone. Those milestones can later be decomposed into smaller `Mx.y` plans if execution pressure or ownership boundaries require it.

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

- `M8.1` `docs/plans/2026-03-30-m8-1-multi-root-model-registry.md`
- `M8.2` `docs/plans/2026-03-30-m8-2-provider-org-model-variant-scanning.md`
- `M8.3` `docs/plans/2026-03-30-m8-3-huggingface-search-pagination-and-cards.md`
- `M8.4` `docs/plans/2026-03-30-m8-4-resumable-downloads-retries-and-mirrors.md`
- `M8.5` `docs/plans/2026-03-30-m8-5-admin-surface-expansion.md`
- `M8.6` `docs/plans/2026-03-30-m8-6-tab-persistence-and-offline-admin-assets.md`
- `M8.7` `docs/plans/2026-03-30-m8-7-model-settings-completion.md`
- `M8.8` `docs/plans/2026-03-30-m8-8-generation-config-and-ocr-sampling-controls.md`
- `M8.9` `docs/plans/2026-03-30-m8-9-homebrew-formula-and-services.md`
- `M8.10` `docs/plans/2026-03-30-m8-10-auto-update-and-startup-failure-handling.md`
- `M8.11` `docs/plans/2026-03-30-m8-11-platform-packaging-and-target-differentiation.md`

## M9: Ecosystem, Agent Integrations, Security, And Stability Completion

- `M9.1` `docs/plans/2026-03-30-m9-1-mcp-tool-loading-and-auto-injection.md`
- `M9.2` `docs/plans/2026-03-30-m9-2-agent-integration-exports.md`
- `M9.3` `docs/plans/2026-03-30-m9-3-additional-api-keys-and-shared-access.md`
- `M9.4` `docs/plans/2026-03-30-m9-4-persistent-sessions-and-remember-me.md`
- `M9.5` `docs/plans/2026-03-30-m9-5-rich-output-sanitization.md`
- `M9.6` `docs/plans/2026-03-30-m9-6-connection-lifecycle-hardening.md`
- `M9.7` `docs/plans/2026-03-30-m9-7-security-and-stability-closure-audit.md`
- `M9.8` `docs/plans/2026-03-30-m9-8-ecosystem-and-security-release-gates.md`

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
