# Issue 42 Unit 2.1.2 Vision Metadata Shape Guards

## Source

- Parent issue: <https://github.com/Keith-CY/melix/issues/1448>
- Governing roadmap: `docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md`
- Prior unit: `docs/plans/2026-05-24-issue-42-u2-1-1-position-metadata-receipts.md`

## Scope

Add worker-local guard receipts for VLM requests whose vision-position metadata
is absent, stale, or unsafe to reuse. This unit keeps the public HTTP,
protobuf, chat, CLI, health, and diagnostics payload shapes unchanged.

The current Python worker does not expose a literal `visual_pos_masks` field.
The equivalent runtime boundary is the shape-only position receipt introduced
in U2.1.1: `position_ids`, `rope_deltas`, media position counts, `cache_offset`,
and `seq_len`. U2.1.2 records when those shapes are safe, absent, or stale
instead of slicing or reusing missing multimodal metadata implicitly.

## Design

- Extend the position metadata receipt with null-safe guard fields:
  `vision_metadata_guard`, `vision_metadata_reuse_allowed`,
  `stale_metadata_fallback_count`, and `companion_rederive_skip_reason`.
- Treat prompt-only and image-free prefills as normal baseline requests:
  no media position state is required, no mismatch is counted, and reuse remains
  allowed for text-only state.
- Replace any previous media-bearing probe receipt when a text-only follow-up
  reaches the VLM runtime, even if a test or legacy caller presents the same
  probe signature. Text-only receipts must not inherit stale media position
  counts or companion skip reasons.
- Treat media-bearing requests without aligned `position_ids` or `rope_deltas`
  as conservative fallback receipts before reuse:
  `vision_metadata_guard=missing_position_metadata`,
  `vision_metadata_reuse_allowed=false`, and
  `stale_metadata_fallback_count=1`.
- Treat media-bearing companion-state rederive as skipped in this worker-local
  unit by recording `companion_rederive_skip_reason=
  multimodal_companion_rederive_skipped_has_media`.

## Performance And Metrics

The guard is receipt-only and runs in constant time over scalar metadata plus
the existing media count. It introduces no tensor tracing, public metrics, or
runtime scheduling work in this unit.

Success metrics:

- Existing VLM fast-path probe tests stay green.
- Image-free / prompt-only VLM tests do not create media sessions or mismatch
  fallback receipts.
- Media-bearing requests with missing position metadata emit a conservative
  worker-local receipt.
- Changed-line coverage for touched Python worker files is at least 95 percent.

## Verification

Run focused Python tests for:

- `services/mlx-worker-python/tests/test_multimodal_position_receipts.py`
- `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_vision_runtime.py`

Before PR handoff, run `git diff --check`, changed-line coverage for touched
files, and a metrics report. The repository pre-commit hook provides the full
local gate and PR-scoped performance report on the macOS 128 GiB host.
