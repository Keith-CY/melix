# Melix Documentation Map

This directory is the system of record for Melix product, architecture, protocol, and execution guidance.

## Precedence

Use documents in this order when resolving ambiguity:

1. `../AGENTS.md`
2. canonical specifications in this directory
3. execution plans in `docs/plans/`
4. templates in `docs/templates/`

## Canonical Specifications

The current top-level specifications remain canonical and should not be moved without an explicit migration task:

- `architecture-spec.md`
- `benchmark-evaluation-contract.md`
- `control-plane-protocol.md`
- `worker-rpc-schema.md`
- `repo-skeleton.md`
- `phase-roadmap.md`

## Planning

Plans live under `docs/plans/`.

Use a plan for non-trivial changes that touch multiple modules, change architecture boundaries, or require staged verification.

Current phase-status and planning documents:

- `plans/2026-03-27-phase-0-thin-path.md`
- `plans/2026-03-27-swift-text-runtime-direction.md`
- `plans/2026-03-28-post-phase-0-coding-milestones.md`
- `plans/2026-03-27-phase-1-swift-text-worker.md`
- `plans/2026-03-28-p2-m1-phase-aware-protocol-shapes.md`
- `plans/2026-03-28-p2-m2-scheduler-lane-read-model.md`
- `plans/2026-03-28-p2-m3-prefill-runtime.md`
- `plans/2026-03-28-p2-m4-decode-and-speculative-runtime.md`
- `plans/2026-03-28-p2-m5-accelerated-prefill-and-active-kv-mode.md`
- `plans/2026-03-28-p2-m6-abort-and-phase-observability.md`
- `plans/2026-03-28-p2-m7-operator-benchmark-evidence.md`
- `plans/2026-03-28-p3-m1-cache-session-contracts.md`
- `plans/2026-03-28-p3-m2-hot-tier-cache-primitives.md`
- `plans/2026-03-28-p3-m3-disk-and-quantized-cache-tier.md`
- `plans/2026-03-28-p3-m4-session-graph-state.md`
- `plans/2026-03-28-p3-m5-recovery-flows.md`
- `plans/2026-03-28-p3-m6-cache-aware-scheduling.md`
- `plans/2026-03-28-p4-m1-endpoint-contract-alignment.md`
- `plans/2026-03-28-p4-m2-responses-endpoint.md`
- `plans/2026-03-28-p4-m3-completions-and-messages-endpoints.md`
- `plans/2026-03-28-p4-m4-reasoning-and-tool-deltas.md`
- `plans/2026-03-28-p4-m5-workflow-aware-shaping.md`
- `plans/2026-03-28-p4-m6-native-desktop-foundation.md`
- `plans/2026-03-28-p5-m1-capability-and-settings-model.md`
- `plans/2026-03-28-p5-m2-embeddings-runtime.md`
- `plans/2026-03-28-p5-m3-rerank-runtime.md`
- `plans/2026-03-28-p5-m4-model-ops-backend.md`
- `plans/2026-03-28-p5-m5-control-plane-endpoints-and-workflows.md`
- `plans/2026-03-28-p5-m6-native-model-tools.md`
- `plans/2026-03-29-p6-m1-multimodal-contracts.md`
- `plans/2026-03-29-p6-m2-ocr-vlm-runtime.md`
- `plans/2026-03-29-p6-m3-audio-runtime.md`
- `plans/2026-03-29-p6-m4-audio-routing-and-endpoints.md`
- `plans/2026-03-29-p6-m5-native-chat-panel.md`
- `plans/2026-03-29-p6-m6-isolation-observability.md`
- `plans/2026-03-29-p6-m7-integration-operator-workflows.md`
- `plans/2026-03-29-p7-m1-image-job-contracts.md`
- `plans/2026-03-29-p7-m2-image-generation-runtime.md`
- `plans/2026-03-29-p7-m3-image-edit-runtime.md`
- `plans/2026-03-29-p7-m4-control-plane-image-orchestration.md`
- `plans/2026-03-29-p7-m5-native-image-panel.md`
- `plans/2026-03-29-p7-m6-isolation-and-cancellation.md`
- `plans/2026-03-29-p7-m7-integration-operator-evidence.md`
- `plans/2026-03-29-p8-m1-native-operator-shell-completion.md`
- `plans/2026-03-29-p8-m2-diagnostics-bench-training.md`
- `plans/2026-03-29-p8-m3-adapter-training-tooling.md`
- `plans/2026-04-01-real-lora-closed-loop.md`
- `plans/2026-03-29-p8-m4-packaging-startup-automation.md`
- `plans/2026-03-29-p8-m5-release-gate-automation.md`
- `plans/2026-03-29-p8-m6-release-runbooks-product-acceptance.md`
- `plans/2026-03-30-full-capability-roadmap.md`
- `plans/2026-03-30-full-capability-roadmap-execution-index.md`
- `plans/2026-03-31-m6-completion-closure.md`
- `plans/2026-03-31-m10-session-lifecycle-and-power-management.md`
- `plans/2026-03-31-m11-disk-streaming-memory-budgeting-and-cache-policy.md`
- `plans/2026-03-31-m12-model-registry-family-coverage-and-model-tools.md`
- `plans/2026-03-31-m13-gateway-configuration-defaults-and-api-onboarding.md`
- `plans/2026-03-31-m14-image-iteration-and-persisted-creative-workflows.md`
- `plans/2026-03-31-m15-desktop-signals-download-recovery-and-streaming-polish.md`
- `plans/2026-03-31-m10-1-session-state-protocol-and-snapshots.md`
- `plans/2026-03-31-m10-2-power-policy-and-lifecycle-controls.md`
- `plans/2026-03-31-m10-3-desktop-status-banners-and-operator-surfaces.md`
- `plans/2026-03-31-m10-4-session-lifecycle-integration-evidence.md`
- `plans/2026-03-31-m11-1-disk-streaming-mode-and-runtime-flags.md`
- `plans/2026-03-31-m11-2-memory-budget-admission-and-safety-guards.md`
- `plans/2026-03-31-m11-3-streaming-cache-compatibility-and-settings-surface.md`
- `plans/2026-03-31-m11-4-large-model-streaming-benchmarks-and-runbooks.md`
- `plans/2026-03-31-m12-1-multi-root-registry-management-and-rescan.md`
- `plans/2026-03-31-m12-2-text-and-moe-family-adapters.md`
- `plans/2026-03-31-m12-3-image-family-dispatch-and-picker-completion.md`
- `plans/2026-03-31-m12-4-model-inspect-health-and-conversion-tools.md`
- `plans/2026-03-31-m13-1-gateway-config-state-model-and-persistence.md`
- `plans/2026-03-31-m13-2-generation-batching-and-speculative-defaults.md`
- `plans/2026-03-31-m13-3-tooling-embedding-and-config-file-settings.md`
- `plans/2026-03-31-m13-4-api-reference-and-quick-start-onboarding.md`
- `plans/2026-03-31-m14-1-image-variation-and-iterate-request-semantics.md`
- `plans/2026-03-31-m14-2-persisted-image-defaults-and-role-aware-picker.md`
- `plans/2026-03-31-m14-3-redo-actions-and-long-running-timeout-policy.md`
- `plans/2026-03-31-m14-4-image-iteration-integration-and-artifact-lineage-evidence.md`
- `plans/2026-03-31-m15-1-token-stream-presentation-smoothing.md`
- `plans/2026-03-31-m15-2-update-banners-and-runtime-signal-unification.md`
- `plans/2026-03-31-m15-3-download-queue-persistence-and-paused-recovery.md`
- `plans/2026-03-31-m15-4-desktop-polish-integration-evidence.md`
- `plans/2026-03-31-m16-video-understanding-and-media-lifecycle.md`
- `plans/2026-03-31-m17-speech-backends-and-voice-catalog.md`
- `plans/2026-03-31-m16-1-video-ingress-and-media-normalization-contracts.md`
- `plans/2026-03-31-m16-2-frame-policy-video-runtime-and-background-lane-routing.md`
- `plans/2026-03-31-m16-3-temporary-media-lifecycle-cleanup-and-failure-recovery.md`
- `plans/2026-03-31-m16-4-video-integration-benchmarks-and-operator-evidence.md`
- `plans/2026-03-31-m17-1-speech-to-text-backend-adapters-and-model-matrix.md`
- `plans/2026-03-31-m17-2-text-to-speech-backend-adapters-and-multilingual-voice-catalog.md`
- `plans/2026-03-31-m17-3-speech-settings-locale-policy-and-optional-dependency-profiles.md`
- `plans/2026-03-31-m17-4-speech-integration-benchmarks-runbooks-and-operator-evidence.md`
- `plans/2026-04-02-m17-mlx-audio-library-integration.md`
- `plans/2026-04-02-m17-audio-runtime-packs-and-managed-model-root.md`
- `plans/2026-03-31-m10-m15-executable-goals.md`
- `plans/2026-03-30-m3-12-protocol-compatibility-test-matrix.md`
- `plans/2026-03-28-p1-m2-swift-text-worker-scaffold.md`
- `plans/2026-03-28-p1-m3-swift-runtime-lifecycle.md`
- `plans/2026-03-28-p1-m4-swift-generate-abort.md`
- `plans/2026-03-28-p1-m5-control-plane-routing.md`
- `plans/2026-03-28-p1-m6-workflow-integration-metrics.md`
- `plans/2026-03-27-phase-2-text-runtime-depth.md`
- `plans/2026-03-27-phase-3-cache-session-recovery.md`
- `plans/2026-03-27-phase-4-text-api-breadth-agent-semantics.md`
- `plans/2026-03-27-phase-5-embeddings-rerank.md`
- `plans/2026-03-27-phase-6-vision-ocr-audio-transcription.md`
- `plans/2026-03-27-phase-7-image-generation-editing.md`
- `plans/2026-03-27-phase-8-desktop-productization-release.md`
- `plans/2026-04-03-bench-matrix-performance-lab.md`

Current roadmap and phase-status documents:

- `phase-roadmap.md`
- `plans/2026-03-27-phase-0-thin-path.md`
- `plans/2026-03-27-phase-1-swift-text-worker.md`

Recent decision records:

- `decisions/2026-03-27-swift-text-runtime.md`
- `decisions/2026-03-28-product-scope-and-runtime-priorities.md`
- `decisions/2026-04-02-m9-security-stability-closure-audit.md`

Current runbooks:

- `runbooks/session-lifecycle.md`
- `runbooks/connection-lifecycle.md`
- `runbooks/admin-surface-persistence.md`
- `runbooks/security-and-stability-closure.md`
- `runbooks/m7-benchmark-and-evaluation-foundation.md`
- `runbooks/m6-acceleration-benchmarks.md`
- `runbooks/homebrew-install.md`
- `runbooks/external-agent-integrations.md`
- `runbooks/service-first-reuse.md`
- `runbooks/shared-access.md`
- `runbooks/persistent-sessions.md`
- `runbooks/rich-output-sanitization.md`
- `runbooks/model-family-support-matrix.md`
- `runbooks/platform-packaging-targets.md`
- `runbooks/phase-1-local-stack.md`
- `runbooks/phase-2-queue-pressure.md`
- `runbooks/phase-6-chat-panel.md`
- `runbooks/phase-6-multimodal-ops.md`
- `runbooks/phase-7-image-ops.md`
- `runbooks/phase-8-local-install.md`
- `runbooks/phase-8-lora-adapter-workflow.md`
- `runbooks/phase-8-release-gates.md`
- `runbooks/phase-8-product-acceptance.md`

## Engineering Standards

Repository-wide engineering rules are defined in:

- `engineering-standards.md`

Use that document for workflow, verification, review, and change-boundary rules.

## Forward Structure

The repository will organize future documents under these paths without moving the current canonical specifications yet:

- `architecture/` for module-level design notes and subsystem breakdowns
- `decisions/` for decision records and irreversible tradeoffs
- `runbooks/` for startup, debugging, and recovery procedures
- `templates/` for reusable planning, architecture, and operations templates

## Operating Constraints

- Formal docs in this repository are written in English.
- Melix naming is the only naming used in formal docs and examples.
- Protocol schemas under `packages/protocol/schema` are the authoritative interface definitions.
- Generated protocol outputs are committed artifacts and must be regenerated when schemas change.
