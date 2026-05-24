# Issue 42 Unit 2.1.3 Mixed-Length Batch Geometry Fixtures

## Source

- Unit issue: <https://github.com/Keith-CY/melix/issues/1449>
- Governing roadmap: `docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md`
- Prior units:
  - `docs/plans/2026-05-24-issue-42-u2-1-1-position-metadata-receipts.md`
  - `docs/plans/2026-05-24-issue-42-u2-1-2-vision-metadata-shape-guards.md`

## Scope

Add worker-local fixture coverage for row-local multimodal batch geometry. This
unit records scalar receipts for mixed-length batch rows so later batch-1 and
continuous-batching fast paths can reject stale prompt kwargs, left-padding,
MRoPE delta, and visual-embed scatter state before reuse.

This unit keeps public HTTP, protobuf, chat, CLI, health, and diagnostics
payload shapes unchanged.

## Design

- Extend the position metadata receipt layer with a mixed-batch geometry helper
  that summarizes each row without retaining tensor payloads.
- Each row receipt records the row index, prompt-kwarg sequence length,
  position-metadata sequence length, cache offset, left-padding width, media
  position count, visual-embed count, MRoPE delta override count, and optional
  row-local identity tokens for MRoPE override and visual-embed scatter state.
- The helper emits stable guard values for:
  - aligned row-local geometry
  - prompt-kwarg sequence drift
  - left-padding drift
  - MRoPE delta drift
  - same-cardinality MRoPE identity drift
  - visual-embed scatter drift
- Three-row fixtures cover text-only, single-image, and heterogeneous
  multi-image rows in one synthetic batch.
- The existing fast-path `multi_image_scatter_mode=per_sample` fixture remains
  row-local evidence that multi-image turns are handled as per-sample scatter.
  This unit does not claim full continuous-batching scatter correctness; it
  records the row-local guard data needed for that later work.

## Performance And Metrics

The helper is fixture/receipt-oriented. It uses scalar counts and shape metadata
already available in tests, and does not inspect full tensor values or run real
MLX kernels.

Success metrics:

- Mixed-length geometry tests do not require GPU or a real `mlx-vlm` model.
- Existing VLM fast-path and position-receipt tests stay green.
- Changed-line coverage for touched Python worker files is at least 95 percent.

## Verification

Run focused Python tests for:

- `services/mlx-worker-python/tests/test_multimodal_position_receipts.py`
- `services/mlx-worker-python/tests/test_multimodal_fast_paths.py`

Before PR handoff, run `git diff --check`, changed-line coverage for touched
files, and a metrics report. The repository pre-commit hook provides the full
local gate and PR-scoped performance report on the macOS 128 GiB host.
