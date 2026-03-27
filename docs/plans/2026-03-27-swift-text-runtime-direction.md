# Melix Swift Text Runtime Direction Plan

**Goal:** Record the selected post-phase-0 runtime direction in the canonical Melix docs before further implementation work begins.

## Summary

- Keep the Swift control plane as the orchestration source of truth.
- Introduce an independent Swift text worker for the default text generation path.
- Keep Python workers for multimodal, embeddings, rerank, image, audio, and maintenance tooling.
- Update the roadmap so the next phase starts with the Swift text `Generate` hot path rather than full phase-aware text depth.

## Planned Changes

1. Add a decision record that captures the selected architecture and the rejected alternatives.
2. Update the architecture spec to describe a polyglot worker pool and the new default text engine direction.
3. Update the repository skeleton to include a Swift text worker service and revised worker ownership boundaries.
4. Update the phase roadmap so Phase 1 reflects the selected rollout strategy.

## Verification

- Confirm the new and updated formal docs are written in English.
- Confirm the docs use Melix naming only.
- Confirm the decision record is linked from the relevant spec or roadmap.

## Metrics Report

- `N/A` for runtime metrics because this change is documentation-only.
