# Issue 42 Unit 2.1.1 Position Metadata Receipts

## Source

- Parent issue: <https://github.com/Keith-CY/melix/issues/1447>
- Governing roadmap: `docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md`

## Scope

Add worker-local VLM position metadata receipts without changing public HTTP,
protobuf, or chat payload shapes. The receipt is shape-only: it records scalar
counts and fallback reasons, never full tensor payloads.

## Design

- Add a small runtime helper that records `position_ids` presence/count,
  `rope_deltas` presence/count, media position count, cache offset, sequence
  length, rebuild count, mismatch fallback count, and fallback reason.
- Store the receipt on `VisionProbeSnapshot` for deterministic and MLX-VLM
  runtimes.
- Emit receipts for normal media requests, prompt-only baseline requests, and
  fallback requests.
- Keep health, CLI, diagnostics, benchmark, and protocol surfaces unchanged in
  this unit. Public projection can be added after the Milestone 1 route/load
  receipt PR lands.

## Performance And Metrics

The hot path work is constant-time over scalar metadata plus a count over media
items already present in `PreparedVisionRequest`. Success metrics:

- No heavyweight tensor tracing is introduced.
- Existing VLM fast-path probe tests remain green.
- Changed-line coverage for touched Python worker files is at least 95 percent.

## Verification

Run focused Python tests for:

- `services/mlx-worker-python/tests/test_multimodal_position_receipts.py`
- `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_vision_runtime.py`

Before handoff, run `git diff --check`, changed-line coverage for touched files,
and a metrics report. A full milestone PR still requires the repository gate
specified in `AGENTS.md`.
