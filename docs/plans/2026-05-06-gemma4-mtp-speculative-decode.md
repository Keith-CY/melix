# Gemma 4 MTP Speculative Decode

## Goal

Enable opt-in Gemma 4 MTP speculative decoding for the Python VLM runtime when
`mlx-vlm` exposes the upstream drafter API, while preserving baseline behavior
for default and unsupported requests.

## Scope

- Reuse the existing worker `AccelerationPolicy` contract:
  `ACCELERATION_MODE_SPECULATIVE_DECODE`, `draft_model_id`,
  `allow_baseline_fallback`, and `num_draft_tokens`.
- Implement the first slice only in `python_vlm` / `MLXVLMRuntime` for prompt-only
  Gemma 4 text-backed generation.
- Runtime-detect upstream `mlx-vlm` support for `generate_step`,
  `batch_generate`, and `load_drafter`; do not add a pinned dependency that is
  unavailable from the current lock resolver.
- Keep speculative decoding disabled unless a request configures a compatible
  target plus assistant pair.
- Reject or baseline-fallback unsupported cases according to
  `allow_baseline_fallback`, including missing drafter APIs, missing draft model,
  non-greedy sampling, non-Gemma targets, and multimodal media inputs.
- Mark Gemma 4 MTP assistant catalog entries as draft-only metadata so they do
  not look like normal serving targets.

## Non-Goals

- No public HTTP API changes or new acceleration mode names.
- No hand-rolled speculative token verification inside Melix.
- No multimodal MTP support until upstream `mlx-vlm` supports media-aware
  drafters through the same stable path.
- No Swift worker DFlash changes in this slice.

## Performance Probes

- Preserve existing VLM preprocessing, media, and first-token probes.
- Runtime events from the MTP path must set the existing speculative fields:
  `speculative_fallback_count`, `speculative_num_draft_tokens`,
  `speculative_draft_model_configured`, and best-effort acceptance/rollback
  fields when upstream returns them.
- Success metric: prompt-only Gemma 4 text-backed requests with a configured MTP
  assistant call upstream drafter decoding with `draft_kind="mtp"` and the
  requested draft block size.

## Implementation Plan

1. Add focused tests for the runtime MTP happy path, fallback and hard-error
   boundaries, engine acceleration-policy forwarding, and assistant catalog
   metadata.
2. Extend `AutoMLXVLMBackend` with optional `generate_step`, `batch_generate`,
   and `load_drafter` hooks plus drafter caching.
3. Route eligible `MLXVLMRuntime.generate_tokens` calls to upstream
   `generate_step(..., draft_kind="mtp")` when available, otherwise to a
   compatible `batch_generate`; otherwise use the existing `stream_generate`
   baseline path or raise a clear error.
4. Forward `ExecutionMetadata.acceleration` from `EngineCore.generate` only to
   runtimes that explicitly accept `acceleration_policy`.
5. Add Gemma 4 assistant metadata detection in the Python model catalog.

## Verification

- Focused pytest for:
  - `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
  - `services/mlx-worker-python/tests/test_generate_stream.py`
  - `services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `make py-test`
- `git diff --check`
- Changed-line coverage over touched Python runtime, engine, catalog, and tests
  at or above `95%`.

## Verification Results

- Focused runtime, engine, and catalog pytest:
  `153 passed, 2 warnings`.
- Full Python worker regression:
  `make py-test` passed with `1802 passed, 5 skipped, 2 warnings`.
- Changed-line coverage for the touched Python scope:
  `95.94%` (`307/320`) for the latest live-MTP validation update.
- Diff hygiene:
  `git diff --check` passed.
- Local runtime capability probe:
  locked `mlx-vlm` is `0.4.4`; `mlx_vlm.generate` exists, but
  `batch_generate` and `mlx_vlm.speculative` are not available in this
  environment. The MTP path is therefore covered with runtime detection and
  fake upstream hooks until the upstream API is present locally.
- Local live model smoke, offline from the Hugging Face cache:
  `unsloth/gemma-4-E4B-it-MLX-8bit` loaded through `MLXVLMRuntime` and
  `AutoMLXVLMBackend` with `runtime_name=mlx-vlm`, `mlx=0.31.2`,
  `mlx-lm=0.31.3`, `mlx-vlm=0.4.4`, and
  `melix.vlm.execution_mode=multimodal`.
- The same live model produced baseline prompt-only text `"Local pass"` with
  `2` token events, `prompt_tokens=17`, `completion_tokens=3`, and
  `first_token_latency_ms=2858.60`.
- A speculative policy against the same live multimodal target with
  `allow_baseline_fallback=true` returned baseline text and surfaced fallback
  metrics on the final token event:
  `speculative_fallback_count=1`, `speculative_num_draft_tokens=0`, and
  `speculative_draft_model_configured=false`.
- The matching hard-error guard with `allow_baseline_fallback=false` raised:
  `MTP speculative decode is unavailable for this request: target execution mode is multimodal.`
- Local live MTP success smoke, offline from the Hugging Face cache, used
  `mlx-community/gemma-4-e4b-it-OptiQ-4bit` as the text-backed target and
  `mlx-community/gemma-4-E4B-it-assistant-bf16` as the MTP drafter. The run used
  a temporary upstream `mlx-vlm 0.5.0` environment because the repository lock
  still resolves `mlx-vlm 0.4.4`.
- The first downloaded upstream `mlx-community/gemma-4-E4B-it-bf16` target was
  rejected for the Melix MTP success path because its cached weights include
  vision and audio modules and therefore load as `multimodal`.
- The live MTP success run loaded the OptiQ target as `text_backed` through
  `MLXVLMRuntime`, routed decoding through upstream
  `generate_step(..., draft_kind="mtp")`, and completed with
  `speculative_draft_model_configured=true`,
  `speculative_fallback_count=0`, and `speculative_num_draft_tokens=6`.
- The same run produced one token event with `prompt_tokens=13`,
  `completion_tokens=8`, `first_token_latency_ms=274.97`,
  `generation_tps=28.95`, and `peak_memory=6.54 GB`.

## Acceptance

- Default VLM generation behavior is unchanged when no speculative policy is
  configured.
- Prompt-only Gemma 4 text-backed generation can use an MTP assistant when the
  upstream drafter API is available.
- Unsupported or unavailable MTP paths produce explicit baseline fallback metrics
  when fallback is allowed and clear runtime errors when fallback is disabled.
- Multimodal media requests do not enter the MTP path in this slice.
