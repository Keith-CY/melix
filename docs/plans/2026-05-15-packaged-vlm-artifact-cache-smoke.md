# Packaged VLM Artifact Cache Smoke

## Goal

Close the next executable slice from issue #58 by proving that packaged VLM
smokes can preserve partial local model artifacts, resume from the same flat
cache, detect the companion projector asset, and emit route receipts for the
local files selected after recovery.

## Scope

- Keep the smoke deterministic and local-file based; do not download from the
  network or start a heavyweight ML runtime.
- Use a flat artifact cache layout for GGUF model and companion projector files.
- Preserve partially downloaded files after cancellation or timeout.
- Reuse the partial cache on the next run instead of starting cold.
- Emit a packaged VLM route receipt with `model_artifact_path`,
  `companion_projector_path`, `cache_layout`, `cache_restore_status`, and
  `local_route_verified`.
- Audit a deterministic text+image prompt through the bundled MLX VLM route and
  record `processor_modality_counts`, `media_token_expansion`,
  `packaged_media_route`, and `unsupported_reason`.

## Out Of Scope

- Live packaged app launch with real VLM inference.
- Hugging Face network download policy changes.
- Broad model registry redesign.

## Performance Probes And Metrics

- `packaged_vlm.cache_restore_success` proves the resumed smoke used the
  preserved partial cache and completed both artifacts.
- `packaged_vlm.partial_cache_bytes_saved` records the bytes preserved after the
  cancelled first pass.
- `packaged_vlm.local_route_verified` proves both the model and projector paths
  resolved from the flat local cache.
- `packaged_vlm.media_token_expansion` records the non-zero media-token
  expansion observed by the packaged audit prompt.
- `packaged_vlm.packaged_media_route_supported` proves the bundled MLX VLM route
  remained admitted after packaging.
- `packaged_vlm.processor_modality_count.{text,image,audio,video}` records the
  processor-visible modality counts used by the audit receipt.

## Verification

- Focused Python tests for the flat cache helper, download pipeline partial
  preservation, and smoke output.
- Changed-scope coverage for touched Python files.
- `git diff --check`.
