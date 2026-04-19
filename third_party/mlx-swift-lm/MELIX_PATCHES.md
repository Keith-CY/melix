# Melix patches for mlx-swift-lm

Vendored from `ml-explore/mlx-swift-lm` at commit:

`5064b8c5d8ed3b0bbb71385c4124f0fc102e74a2`

Melix patches:

- Add `fusedQ4ScaledDotProductAttention` for affine q4 one-token decode over MLX quantized KV-cache state.
- Route `attentionWithCacheUpdate` through the fused q4 decode kernel when the quantized cache state is supported, otherwise preserve the upstream quantized attention fallback.
- Add a per-cache fused attention dispatch counter so Melix runtime metrics only report `active_kv_kernel_path=fused` after the fused dispatch actually runs.
- Add per-cache fused attention timing counters and a recording hook so Melix can report fused route wall time separately from MLX model evaluation sync time.
- Add `QuantizedKVCache.updateQuantizedStorage(...)` so the fused route can consume preallocated quantized cache storage with an explicit effective sequence length instead of materializing trimmed q4 state for every decode token.
- Shorten q4 storage appends to direct 3-axis slice updates for the routed fused path.
- Add an experimental `fusedQ4AffineKeyValueQuantizedForDecode(...)` q4 affine key/value decode quantizer, including bfloat16 output casting, gated by `MELIX_SWIFT_TURBOQUANT_FUSED_QUANTIZE=1` because real-model metrics show it is slower than MLX native `quantized(...)`.
