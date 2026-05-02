# Melix patches for mlx-swift-lm

Upstream alignment target:

- `ml-explore/mlx-swift-lm` tag `2.31.3`
- tag commit `25b00d4e22e61ec9c41efda47990cd2084ec87ff`

The local tree retains Melix runtime patches on top of the upstream 2.x line.

Melix patches:

- Add `fusedQ4ScaledDotProductAttention` for affine q4 one-token decode over MLX quantized KV-cache state.
- Route `attentionWithCacheUpdate` through the fused q4 decode kernel when the quantized cache state is supported, otherwise preserve the upstream quantized attention fallback.
- Add a per-cache fused attention dispatch counter so Melix runtime metrics only report `active_kv_kernel_path=fused` after the fused dispatch actually runs.
- Add per-cache fused attention timing counters and a recording hook so Melix can report fused route wall time separately from MLX model evaluation sync time.
- Add per-cache fused attention launch and softmax-lane counters so Melix can compare active lanes, launched lanes, inactive lanes, softmax lanes, and softmax token-lane work before and after kernel layout changes.
- Add `QuantizedKVCache.updateQuantizedStorage(...)` so the fused route can consume preallocated quantized cache storage with an explicit effective sequence length instead of materializing trimmed q4 state for every decode token.
- Shorten q4 storage appends to direct 3-axis slice updates for the routed fused path.
- Update dynamic KV quantization to scan mixed cache arrays per layer, preserving Mamba-style cache entries while quantizing eligible `KVCacheSimple` full-attention entries for Qwen3.5-style hybrid models.
- Add an experimental `fusedQ4AffineKeyValueQuantizedForDecode(...)` q4 affine key/value decode quantizer, including bfloat16 output casting, gated by `MELIX_SWIFT_TURBOQUANT_FUSED_QUANTIZE=1` because real-model metrics show it is slower than MLX native `quantized(...)`.
- Optimize the fused q4 decode attention kernel by computing online-softmax state on one lane and broadcasting it to value lanes, and by hoisting each lane's eight query values out of the historical-token loop. The single-lane online-softmax design is intentional for the current 4096-token cap; raising that cap should revisit a two-pass or parallel softmax reduction.
- Keep `fusedQ4AffineKeyValueQuantizedForDecode(...)` opt-in and scoped to the fused decode contract; its packed/scales/biases output is validated by Melix tests but should be revalidated before any new non-fused consumer reuses it.
- Keep the DFlash draft runtime and Qwen3/Qwen3.5 hidden-state hooks used by Melix speculative decode tests.
- Carry the upstream 2.31.x Swift 6.1 concurrency compatibility surface for
  `ModelContainer`, `UserInputProcessor`, `MessageGenerator`, and async
  generation task capture while preserving Melix's existing service call paths.
