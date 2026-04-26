# Issue 42 Multimodal Fast Paths

## Source

- GitHub issue: <https://github.com/Keith-CY/melix/issues/42>
- Branch: `codex/issue-42-multimodal-fast-paths`

## Goal

Add a Melix-owned fast-path layer around the pinned `mlx-vlm` runtime so VLM
execution is observable and can safely select optimized paths without changing
the public multimodal API.

The first staged milestone is observability plus conservative admission:
supported multimodal families report selected decode and quantized-load modes,
repeated images report feature-cache reuse, and unsupported paths emit explicit
fallback receipts instead of silently looking optimized.

## Public Interface Boundary

- No HTTP request or response shape changes.
- No protobuf schema changes.
- No chat payload changes.
- New externally visible surface is benchmark metrics and phase-6 evidence JSON.

## Internal Modes

The Python VLM runtime records these internal mode values:

- `baseline`: no media fast path is needed.
- `single_stream`: supported image prompt with no reusable image features.
- `image_cache_reuse`: at least one image feature key was reused.
- `native_quantized`: supported quantized multimodal load is admitted on the pinned backend.
- `fallback`: the request cannot use the fast path and carries an explicit reason.

## Cache Key Contract

Per-image feature reuse is keyed by:

- image SHA-256
- vision family id
- multimodal adapter hash
- preprocessing fingerprint, currently prompt profile, tokenization mode, image
  limit, image MIME type, and image format
- quant profile id

The key is per image, not per prompt. Multi-image turns can therefore partially
reuse repeated images while recording misses for new images in the same request.

## Fallback Contract

Fallbacks are expected, not exceptional, for unsupported cases:

- `text_backed_no_vision_weights`: text-backed Gemma 4 image requests retain the
  safe baseline behavior and fail only at generation, as before.
- `unsupported_family`: the pinned dependency does not have a supported family
  fast-path contract.
- `video_fast_path_unimplemented`: video-only VLM requests remain outside this
  image-feature fast path.
- `not_quantized` and `unsupported_quant_profile`: quantized-load admission did
  not apply.

## Metrics And Evidence

Runtime probes, VLM benchmark output, and phase-6 evidence reports expose:

- `image_feature_cache_hits`
- `image_feature_cache_misses`
- `multimodal_decode_mode`
- `multimodal_fallback_reason`
- `multimodal_decode_sync_mode`
- `multi_image_scatter_mode`
- `quantized_load_mode`
- `quantized_load_fallback_reason`

Benchmark metrics are numeric and encode categorical fields as stable codes.
Phase-6 evidence JSON preserves the string values. The live control-plane metrics
export remains limited to the existing numeric `RuntimeStats` bridge until a
separate protocol change is explicitly accepted.

## Implementation Slices

1. Add fast-path unit coverage for mode selection, fallback receipts, repeated
   image reuse, partial multi-image reuse, text-only turns, and quantized-load
   admission.
2. Add `worker.runtime.multimodal_fast_paths` and wire it into deterministic and
   `mlx-vlm` runtime probes.
3. Extend VLM benchmark reporting with cache hit/miss counters and categorical
   fast-path code metrics.
4. Extend phase-6 evidence reports and runbook documentation.
5. Stage speculative/drafter work only as probe-only follow-up after batch-1
   decode and image-cache correctness remain green under real VLM models.

## Performance Probes

- Batch-1 VLM decode: `bench.<suite>.image_ttft_ms` and
  `bench.<suite>.vlm_tokens_per_second`.
- Repeated-image conversations: `bench.<suite>.image_feature_cache_hits` and
  `bench.<suite>.image_feature_cache_misses`.
- Multi-image heterogeneous prompts: `bench.<suite>.multi_image_scatter_mode`.
- Quantized multimodal loads: `bench.<suite>.quantized_load_mode` and
  `bench.<suite>.quantized_load_fallback_reason`.
- Mixed-mode benchmark suites: categorical VLM fast-path metrics must report a
  distinct mixed code instead of inheriting only the final sample's mode.

Live speedup claims require a real MLX multimodal model. Deterministic tests only
prove admission, fallback, cache-key, and evidence correctness.

## Verification

Required before PR handoff:

- `make proto`
- `make py-test`
- targeted Python tests with the `mlx` extra when a real `mlx-vlm` environment is
  available
- `make integration-test`
- changed-line coverage at or above 95 percent, or an explicit N/A report if the
  touched path is not currently measurable
- metrics report for the touched scope

## Current Gaps

- The first stage does not patch upstream `mlx-vlm` generation internals.
- String fast-path modes are not exported through `RuntimeStats` because this
  plan intentionally keeps protobuf unchanged.
- Throughput improvements are not claimed until live baseline and post-change
  benchmark artifacts exist for the same pinned model.
