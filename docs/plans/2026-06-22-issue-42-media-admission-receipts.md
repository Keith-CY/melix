# Issue 42 Media Admission And Processor Receipts

## Source

- GitHub issue: <https://github.com/Keith-CY/melix/issues/42>
- Governing roadmap: `docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md`
- Related units:
  - Unit 1.1.3, fail closed for media-present requests on text-only runtimes.
  - Unit 1.3.1, surface route, media count, cache count, unsupported reason, and fallback receipts.
  - Unit 3.1.1, replace feature-key-only receipts with a real media-feature cache for supported image-family preprocessing contracts.
- Prior slice: PR #2244, stream finalizer cache residency.

## Goal

Tighten multimodal admission around the next Issue 42 watch finding: media
requests must fail before text-only prompt conversion, while supported VLM
requests must include processor-shape policy in the request receipt and image
feature cache identity.

This slice is still an admission and receipt hardening step. It does not claim a
new decode throughput improvement or introduce a real image-feature store.

## Architecture

`EngineCore.generate()` is the shared worker entry point for streamed generation
and already knows the loaded runtime kind before prompt rendering. It should
reject media-bearing messages when the active runtime is not a media-capable
runtime before calling `runtime.render_prompt()`, so adapter-level text prompt
conversion cannot silently drop image or video parts.

The deterministic VLM runtime already records fast-path probes and feature-cache
hit/miss counters. The existing VLM family contract owns prompt profile,
tokenization mode, image budget, and adapter hash. This slice extends that same
contract with a processor-shape receipt:

- `processor_policy`
- `media_count`
- `crop_grid`
- `patch_size`
- `max_crop_count`
- `prompt_format`
- `projected_feature_shape`

The VLM fast-path cache signature must include the processor-shape fields so a
repeated image can hit only when the effective processor policy matches.

## Test Plan

Add worker/runtime regression coverage that:

1. Loads a text-only model and sends an image-bearing generate request. The
   request returns a typed `unsupported_media` error with model/runtime/media
   receipt details before prompt conversion.
2. Loads a supported deterministic VLM model, runs a repeated image request, and
   asserts the probe records the processor policy, crop grid, media count, and
   feature-cache hit/miss counters.
3. Runs the same image through two VLM model contracts with different processor
   shape metadata and asserts the second request misses rather than reusing the
   first processor-shape cache key.

## Performance Probes And Success Metrics

- Text-only media requests report zero adapter-side media drops by rejecting
  before prompt rendering.
- Supported VLM probes expose processor-shape fields alongside existing
  image-feature cache hit/miss counters.
- Repeated-image cache tests prove cache hits require matching processor-shape
  receipts.
- Changed-scope Python coverage for touched files must be at least 95 percent,
  or the PR evidence must explain why the changed path is not measurable.

## Verification

Required focused checks before PR handoff:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_media_admission_receipts.py services/mlx-worker-python/tests/test_multimodal_fast_paths.py services/mlx-worker-python/tests/test_vision_runtime.py::test_vlm_completion_token_count_scans_without_split_list services/mlx-worker-python/tests/test_vision_runtime.py::test_vlm_generate_reuses_prompt_token_count_for_probe_and_event services/mlx-worker-python/tests/test_vision_runtime.py::test_vlm_runtime_reuses_cached_snapshot_between_stats_reads services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_mlx_vlm_runtime_caches_family_config_across_prompt_render_and_token_count`
- Changed-scope coverage for touched Python files.
- Registered PR-scoped performance probes selected by the touched files.

## Non-Goals

- No protobuf schema change.
- No public chat or responses payload shape change.
- No real media-feature store replacement.
- No native VLM throughput claim.
- No speculative multimodal decode behavior change.
