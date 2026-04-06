# Task Plan

## Goal

Close `M16.2` by making video analysis requests carry an explicit frame policy through the
effective multimodal request state, route predictably through background vision lanes, and expose
runtime probe evidence that distinguishes video analysis from image-only VLM work.

## Scope

- extend multimodal preprocessing so `PreparedVisionRequest` can carry normalized video inputs and
  an inspectable effective frame policy
- shape deterministic and MLX VLM runtimes around the same video-aware request representation
- project video analysis observability into the control plane without changing media-lifecycle
  cleanup behavior
- add focused worker, control-plane, and integration coverage for background-lane routing and video
  probe evidence

## Measurement Points

- video-bearing requests normalize into one effective request object that preserves prompt text,
  image inputs, video inputs, total preprocessing bytes, and frame-policy details
- video analysis keeps using the explicit `multimodal.vision.background` lane and does not reuse
  interactive text-prefill lanes
- runtime observability records video preprocess latency, effective frame count, and first-token
  latency for VLM requests that include video parts
- changed-line coverage for the touched executable scope remains at or above `95%`

## Phases

1. Current-state review and M16.2 boundary lock
   - status: completed
   - evidence:
     - reviewed `M16.2` and the parent `M16` plan plus the current Swift request-routing,
       multimodal normalization, worker preprocessing, VLM runtimes, and integration coverage
     - confirmed that `M16.1` ended at ingress contracts only and that `M16.2` should stop before
       temp-media lifecycle cleanup (`M16.3`)
2. Video-aware worker request shaping
   - status: completed
   - evidence:
     - `PreparedVisionRequest` now carries normalized `videos`, explicit
       `video_frame_policies`, and derived `effective_video_frame_count`,
       `requested_video_frame_budget`, and `effective_video_window_ms` helpers
     - multimodal preprocessing now folds `prepare_video_input` into the shared vision request
       path, computes one inspectable effective frame policy per video input, and rebuilds the
       multimodal hash from prompt plus image or video identity
     - deterministic and MLX VLM runtimes now consume the same video-aware request shape,
       including text-backed Gemma 4 prompt rewriting for video-only requests
3. Runtime probe and background-lane observability
   - status: completed
   - evidence:
     - worker runtime stats now export `last_video_effective_frame_count`,
       `last_video_requested_frame_budget`, and `last_video_window_ms`
     - video-bearing VLM prefill or decode requests still route through
       `multimodal.vision.background`, while `RequestCoordinator` publishes explicit video frame and
       first-token metrics for that lane
     - the Swift text worker now explicitly ignores video fragments for cache-restore prefix walks
       and counts them as media tokens in context guards, keeping protocol exhaustiveness intact
4. Focused verification and roadmap bookkeeping
   - status: completed
   - evidence:
     - `make proto`: pass
     - `make py-test`: `525 passed in 35.75s`
     - `make integration-test`: `71 passed in 1079.85s (0:17:59)`
     - focused Swift coverage-enabled verification:
       `swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'videoBearingVLMRequestsPublishFramePolicyMetrics|postChatCompletionsRecordsVideoFrameMetricsForVLMRequests'`
       and
       `swift test --enable-code-coverage --package-path services/mlx-text-worker-swift --filter 'testCacheRestoreMetadataWalkBackAccountsForMediaPrefixesAndIgnoresNilParts|testRuntimeRegistryCountsMediaBlankAndNilPartsForContextGuard'`
       both passed
     - touched-scope changed-line coverage is at or above `95%` for Python, control plane, and
       Swift text-worker scope; repository bookkeeping is updated in `progress.md` and the roadmap
       execution index

## Acceptance

- Melix exposes one effective request shape for image and video VLM analysis with explicit video
  frame-policy state
- video-bearing VLM requests remain schedulable through the background vision lane with measurable
  preprocess and first-token behavior
- verification proves the touched scope at or above `95%` changed-line coverage before commit

## Risks

- if video preprocessing lives outside the shared vision request model, runtime and benchmark paths
  will fork on transport details
- if background-lane observability only reports image semantics, later video queue-pressure work
  will lack trustworthy evidence
- if `M16.2` reaches into temp-file cleanup or download lifecycle behavior, it will blur the
  boundary with `M16.3`
