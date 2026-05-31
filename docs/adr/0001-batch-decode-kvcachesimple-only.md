# Batch decode restricted to KVCacheSimple sessions

The Swift text worker's `decodeBatchEvents` implementation only batches sessions whose prefill produced `KVCacheSimple` caches. Sessions using `RotatingKVCache` (sliding-window models) fall back to the single-request decode path.

**Why:** Batching N requests into one forward pass requires assembling N per-request KV caches into a single padded batched cache with shape `[N, kvHeads, max_offset, head_dim]`. `KVCacheSimple` exposes its key/value tensors through the standard `state: [MLXArray]` property, making extraction and left-padding straightforward. `RotatingKVCache` maintains a circular write pointer and evicts old tokens — stacking evicted caches with padding produces incorrect attention over the available window, so batching is not safe without re-prefilling the shorter session.

**Considered alternatives:**
- *Re-prefill on join* — when a `RotatingKVCache` session joins a batch, re-prefill it to produce a compatible `KVCacheSimple` cache. Correct, but adds latency proportional to prompt length on every batch join.
- *Interleaved sequential decode* — run N single-request decode steps in a round-robin loop instead of one batched forward pass. Avoids the cache-type problem entirely but does not amortize model weight loads, so total throughput is unchanged.

**Consequence:** Models that default to `RotatingKVCache` (e.g. those with a sliding-window attention config) do not benefit from batch decode. The eligibility check in `TextDecodeEngine.makeBatchCandidateIfEligible` gates on `decodeState.cache.allSatisfy({ $0 is KVCacheSimple })` to enforce this at admission time.

**Known approximation:** The assembled batched cache left-pads shorter sessions with zeros but does not pass a corresponding attention mask to the model. Shorter sessions attend over padding positions; in practice the zero-padded keys produce near-zero attention scores and the quality impact is small for typical interactive batch sizes (2–4). A future fix would pass an explicit `[N, 1, 1, max_offset]` causal mask in `LMInput.Text.mask`.
