# Qwen3.6 Native MTP Serving Parity

## Goal

Make Qwen3.6 native multi-token prediction usable in Melix for text-only VLM
serving, then compare the same model, prompt profile, and acceleration setting
against OMLX until Melix is faster on the measured serving scenarios.

## Current Evidence

- The local base checkpoint
  `unsloth/Qwen3.6-27B-UD-MLX-4bit` declares
  `text_config.mtp_num_hidden_layers=1`, but its safetensors index contains no
  `mtp.*` weights.
- Loading that base checkpoint with native MTP enabled fails because the runtime
  expects the missing MTP head tensors.
- The separate `guru87/Qwen3.6-27B-MTP` head provides the 15 missing BF16 MTP
  tensors.
- A temporary fused snapshot only loads in the local MLX VLM stack when both the
  safetensors header and the model index expose those tensors as
  `language_model.mtp.*`.
- The unconverted BF16 head loads in OMLX but produced `accept=0/62 (0.0%)` on
  a 64-token text-only request.
- Applying the MLX RMSNorm conversion (`+1`) to the seven MTP norm tensors
  changed OMLX acceptance to `accept=28/34 (82.4%)` and reduced the same
  64-token request from `43.85s` to `18.23s`.
- The same converted fused snapshot still fails in Melix today with
  `Received 15 parameters not in model: language_model.mtp.*`, proving Melix
  lacks the native MTP model/runtime patch before load.

## Scope

- Add a Melix-owned native MTP runtime patch for Qwen3.5/Qwen3.6 MLX VLM
  classes and the `mlx-lm` `BatchGenerator` dispatch path.
- Gate native MTP activation by model/request metadata so baseline behavior and
  unsupported models remain unchanged.
- Keep the first implementation slice focused on text-only VLM requests through
  the existing cooperative `BatchGenerator` path.
- Surface native MTP acceptance/rollback counters through the existing runtime
  speculative fields when the patched generator can report them.
- Add a small model-artifact helper for local Qwen3.6 MTP head injection only if
  needed for reproducible local benchmark setup.

## Non-Goals

- No new public acceleration mode name in this slice.
- No multimodal native MTP path until text-only serving is stable.
- No hand-written replacement for all upstream speculative decoding logic beyond
  the minimal runtime patch needed by the current locked MLX dependencies.
- No UI changes.

## Performance Probes

- Load-time metadata must report whether native MTP was detected, whether the
  MTP head was attached, and whether the text-only batch generator can activate
  it.
- Runtime events must preserve existing fields:
  `speculative_acceptance_rate`, `speculative_rollback_rate`,
  `speculative_accepted_tokens`, `speculative_rejected_tokens`,
  `speculative_fallback_count`, `speculative_num_draft_tokens`, and
  `speculative_draft_model_configured`.
- Text native-MTP runtime events must split the fixed-cost path into
  preparation, prompt encoding, external prompt prefill, `BatchGenerator.insert`,
  first response, and first visible segment timings so OMLX parity work can
  distinguish prompt setup, prefill, and stream-delivery overhead.
- Benchmark artifacts must include OMLX and Melix endpoint metrics, memory use,
  acceleration state, and the MTP acceptance counters.
- Text-route streaming metrics must separate user-visible stream completion
  from post-response worker/cache observability refresh so HTTP total latency
  does not include non-response cleanup work. Multimodal/audio/image routes
  keep synchronous refresh because their user-facing probes are emitted from
  runtime stats.

## Success Metrics

- Melix can load the converted Qwen3.6 fused MTP snapshot without unmatched MTP
  weight errors.
- A text-only greedy request activates native MTP and records non-zero
  acceptance on a prompt where OMLX records non-zero acceptance.
- The first live VLM text-only path is usable, but direct component timings
  show the remaining gap is concentrated in the VLM wrapper's MTP
  verify-backbone forward rather than the BatchGenerator draft/verify loop.
- The Python text native-MTP route reuses its loaded-model `BatchGenerator`
  across requests and closes it when the model is unloaded, matching the
  OMLX scheduler lifecycle closely enough for single-request serving parity.
- Text-route terminal delivery closes the client stream before post-response
  observability refresh; a blocking runtime stats probe must not delay the
  final SSE `[DONE]` path.
- Melix beats OMLX on the same Qwen3.6 native-MTP configuration for the chosen
  warm streaming scenarios, with no request errors.

## Implementation Plan

1. Add focused tests for pre-load native MTP patch dispatch and text-only
   batch-generator activation metadata.
2. Add a native MTP patch package under the Python worker runtime, applying the
   Qwen3.5/Qwen3.6 VLM class patch before `mlx_vlm.load()`.
3. Wire `AutoMLXVLMBackend.load_model()` to detect compatible Qwen3.6 native
   MTP models from `config.json` and model metadata, then apply the patch before
   loading.
4. Extend `_TextOnlyBatchGeneratorScheduler` events so patched native-MTP
   generator statistics can be emitted through existing speculative fields.
5. Run the live Qwen3.6 fused-MTP Melix smoke, then the OMLX-vs-Melix benchmark
   harness with identical model settings.
6. Add a Python text-runtime native-MTP path for Qwen3.5/Qwen3.6 using the same
   mlx-lm `BatchGenerator` dispatch and model-side MTP hooks, so pure-text
   Qwen3.6 serving can bypass the VLM wrapper when the model manifest declares
   `model_kind: "text"` and `melix.capability.route_kind:
   "python_text_compatibility"`.
7. Move non-multimodal text-route post-response observability refresh off the
   client stream critical path while preserving synchronous runtime metric
   publication for multimodal/audio/image routes.

## Verification

- Focused pytest for:
  - `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
  - any new native MTP helper tests
- Live local smoke using the converted Qwen3.6 fused MTP snapshot.
- OMLX-vs-Melix serving comparison report for the same model and generation
  settings.
- `make py-test` before handoff or PR.
- Changed-scope coverage and metrics report at or above repository handoff
  requirements before any commit.
