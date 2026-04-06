# M16.2 Frame Policy, Video Runtime, And Background-Lane Routing

## Goal

Make frame selection, runtime shaping, and scheduler behavior explicit for video analysis so video requests can coexist with text and image workloads predictably.

## Scope

- add frame-sampling and frame-budget policy
- route video workloads through explicit background lanes
- expose queue, pressure, and first-token metrics for video analysis

## Files

- update `services/control-plane-swift/Sources/EnginePool/`
- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/engine/`
- update `tests/integration/`

## Implementation Notes

- Video frame policy should remain configuration-driven and visible in effective request state.
- Video analysis must not reuse interactive text lanes implicitly.

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`

## Acceptance

- Video requests use explicit frame policy and background-lane routing.
- Queue and latency behavior are measurable under concurrent text load.

## Completion Notes

- Melix now carries one shared effective request shape for image and video VLM analysis:
  `PreparedVisionRequest` preserves normalized `images`, normalized `videos`, explicit
  `video_frame_policies`, and derived frame-budget or time-window helpers.
- Deterministic and MLX VLM runtimes now project the same video-aware request state into runtime
  probes, including text-backed Gemma 4 prompt rewriting for video-only requests and explicit video
  probe fields in worker runtime stats.
- The Swift control plane keeps video-bearing VLM requests on
  `multimodal.vision.background` and now records video-specific metrics from the authoritative
  worker probe snapshot:
  - `vision.video_frame_count`
  - `vision.video_frame_budget`
  - `vision.video_window_ms`
  - `vision.video_first_token_ms`
- The Swift text worker now treats `videoUri` and `videoBytes` parts as media for context guards
  while ignoring them for cache-restore prefix reuse, preserving protocol exhaustiveness after the
  video-aware worker-probe expansion.

## Verification Evidence

- `make proto`
  - pass
- `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_video_preprocessing.py services/mlx-worker-python/tests/test_vision_runtime.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py -q`
  - `49 passed in 0.23s`
- `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_vision_runtime.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py -q`
  - `46 passed in 0.16s`
- `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest tests/integration/test_vlm_phase_aware_lifecycle.py -q`
  - `3 passed in 34.20s`
- `make py-test`
  - `525 passed in 35.75s`
- `make integration-test`
  - `71 passed in 1079.85s (0:17:59)`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'videoBearingVLMRequestsPublishFramePolicyMetrics|postChatCompletionsRecordsVideoFrameMetricsForVLMRequests'`
  - `2 tests in 2 suites passed`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path services/mlx-text-worker-swift --filter 'testCacheRestoreMetadataWalkBackAccountsForMediaPrefixesAndIgnoresNilParts|testRuntimeRegistryCountsMediaBlankAndNilPartsForContextGuard'`
  - `2 tests in 1 suite passed`
- `make swift-test`
  - failed outside the touched M16.2 scope after package-level execution completed; the
    touched control-plane and text-worker suites above both passed with coverage enabled

## Metrics

- Python touched-scope changed-line coverage:
  - `100.00%` (`148/148`)
- Swift control-plane touched-scope changed-line coverage:
  - `100.00%` (`197/197`)
- Swift text-worker touched-scope changed-line coverage:
  - `100.00%` (`15/15`)
