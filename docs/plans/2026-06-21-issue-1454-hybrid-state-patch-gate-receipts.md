# Issue 1454 Hybrid-State Patch/Gate Receipts

## Source

- GitHub issue: <https://github.com/Keith-CY/melix/issues/1454>
- Governing roadmap: `docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md`
- Parent tracker: <https://github.com/Keith-CY/melix/issues/1431>

## Goal

Add family-scoped hybrid-state patch and gate receipts for multimodal VLM fast
paths. The receipt must prove cache advance, contiguous state, and text-only
RoPE decisions before a request enters a default fast path. Unsupported
hybrid-state paths must fall back with an explicit override count instead of
looking like an optimized route.

## Scope

- Extend the multimodal fast-path decision with hybrid-state patch mode,
  cache-advance count, and family fast-path override count.
- Add a worker-side hybrid-state receipt builder alongside the existing
  position metadata and quantized KV mask receipts.
- Surface the receipt on deterministic VLM probe snapshots and expose
  `vision.hybrid_state_patch_mode`, `vision.hybrid_state_advance_count`, and
  `vision.family_fast_path_override_count` through the runtime metrics path.
- Add focused tests for variable-length multimodal rows, unsupported fallback
  gates, deterministic VLM probes, runtime stats propagation, and phase-6
  metrics defaults.

## Out Of Scope

- Real backend hybrid-cache mutation.
- New public chat request or response fields.
- Promoting any image-bearing batch-1 or speculative multimodal decode route.

## Performance Probes

- Local scoped performance report selected by changed files before commit.
- Acceptance metric presence is verified in focused tests; the new counters are
  categorical/count metrics and should not alter decode work.
- Success means no in-scope regression in the pre-commit performance report and
  no remote PR performance regression.

## Verification

1. Run focused Python tests for multimodal receipts, fast-path admission,
   runtime stats, and acceptance metrics.
2. Run focused Swift metrics tests that publish the new runtime metrics.
3. Regenerate protobuf artifacts after schema changes.
4. Run changed-scope coverage and the repository pre-commit gate before commit.
