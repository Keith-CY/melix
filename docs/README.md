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

Current roadmap and phase-status documents:

- `phase-roadmap.md`
- `plans/2026-03-27-phase-0-thin-path.md`
- `plans/2026-03-27-phase-1-swift-text-worker.md`

Recent decision records:

- `decisions/2026-03-27-swift-text-runtime.md`
- `decisions/2026-03-28-product-scope-and-runtime-priorities.md`

Current runbooks:

- `runbooks/phase-1-local-stack.md`
- `runbooks/phase-2-queue-pressure.md`

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
