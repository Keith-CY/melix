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

- Current dependency state as of 2026-05-23:
  `services/mlx-worker-python/pyproject.toml` requires `mlx-vlm>=0.5.0,<0.6`
  and `uv.lock` resolves `mlx-vlm 0.5.0`. The main Gemma 4 MTP execution path
  is already present on `origin/main` from the earlier Gemma 4 MTP slice; the
  2026-05-23 follow-up does not reimplement routing. It only closes the
  generate-step observability gap by copying upstream drafter `accept_lens`
  statistics into the existing runtime speculative fields.
- Current OMLX validation used `/Users/chenyu/Documents/github/omlx` at
  `2f2f5087a9c9a6ef71fa165da4a299bd19d4d5b4` with `omlx=0.3.9`, `mlx=0.31.2`,
  `mlx-lm=0.31.3`, and `mlx-vlm=0.5.0`.
- Current local cache state before the online drafter probe had the E4B target
  cached but no E4B assistant drafter. The online drafter probe downloaded and
  loaded `mlx-community/gemma-4-E4B-it-assistant-bf16` as an MTP drafter with
  `model_type=gemma4_assistant`; the cached assistant directory is about
  `182M`.
- Current OMLX baseline-vs-MTP comparison used target
  `unsloth/gemma-4-E4B-it-MLX-8bit`, drafter
  `mlx-community/gemma-4-E4B-it-assistant-bf16`, port `18062`, greedy sampling,
  `max_tokens=96`, and three repeats. Runtime evidence lives under
  `.runtime/gemma4-assistant-omlx-validation/evidence/omlx/`.
- OMLX MTP server logs prove the full route: settings loaded, the drafter
  loaded as `kind=mtp`, the scheduler and engine attached the drafter, and each
  request emitted `vlm_mtp decode started` plus `vlm_mtp stats`.
- OMLX warm baseline results averaged `1.192051s` total duration,
  `0.057557s` content TTFT, `80.53` conservative decode tok/s, and `84.53`
  usage tok/s.
- OMLX warm MTP results averaged `1.011354s` total duration, `0.054818s`
  content TTFT, `94.93` conservative decode tok/s, and `100.37` usage tok/s.
  This is a `15.16%` warm-duration reduction, `17.88%` conservative tok/s lift,
  and `18.73%` usage tok/s lift versus baseline.
- OMLX MTP acceptance evidence was stable across all three requests:
  `rounds=40`, `accepted=56/200 (28.0%)`, `tokens_per_round=2.40`,
  `emitted=96`, and `block_size=6`.
- The current Melix follow-up mirrors that OMLX acceptance accounting for the
  `generate_step` path by reading drafter `accept_lens` after generation and
  publishing `speculative_acceptance_rate`, `speculative_rollback_rate`,
  `speculative_accepted_tokens`, and `speculative_rejected_tokens` on the final
  `RuntimeTokenEvent` when upstream exposes the data.

Historical implementation-slice verification:

- Focused runtime, engine, and catalog pytest:
  `153 passed, 2 warnings`.
- Full Python worker regression:
  `make py-test` passed with `1802 passed, 5 skipped, 2 warnings`.
- Changed-line coverage for the touched Python scope:
  `95.94%` (`307/320`) for the latest live-MTP validation update.
- Diff hygiene:
  `git diff --check` passed.
- Local runtime capability probe:
  the original implementation slice was first validated in an environment where
  the repository lock still resolved `mlx-vlm 0.4.4`; the current repository
  lock now resolves `mlx-vlm 0.5.0`.
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
