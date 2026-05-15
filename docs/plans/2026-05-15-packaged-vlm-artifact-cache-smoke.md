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

## Verification

- Focused Python tests for the flat cache helper, download pipeline partial
  preservation, and smoke output.
- Changed-scope coverage for touched Python files.
- `git diff --check`.
