# Issue 42 U2.2.2 Chunked Auxiliary Tensor Slicing

## Source

- GitHub issue: <https://github.com/Keith-CY/melix/issues/1451>
- Parent plan: <https://github.com/Keith-CY/melix/issues/1430>
- Governing roadmap: `docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md`
- Prior slice: `docs/plans/2026-05-24-issue-42-u2-2-1-attention-cost-auto-chunk-policy.md`

## Goal

Keep prompt-length-aware auxiliary tensors aligned with `inputs_embeds` during
chunked VLM prefill by slicing them with the same `cache_offset:cache_offset +
seq_len` window before each forward pass.

## Architecture

This remains a Python worker runtime change. The worker already selects
`prefill_step_size` from the attention-budget policy and is the last Melix-owned
boundary before the pinned `mlx-vlm` backend enters prefill. The implementation
adds a worker-local slicing helper for prompt-length-aware kwargs and uses it
from Melix's VLM runtime tests and backend adapters where chunked prefill kwargs
are assembled.

The pinned `mlx-vlm` 0.5.0 implementation chunks `input_ids` and
`inputs_embeds` in single-request `generate_step`, and its batch prompt
generator slices only tensors it recognizes as sequence-aligned on the second
axis. Melix therefore records and verifies the stricter contract locally:
`position_ids` and similar prompt-length-aware tensors are sliced by explicit
cache offsets instead of relying on exact-length assumptions or a fixed axis.

## Prompt-Length-Aware Tensor Contract

- `inputs_embeds` is sliced on prompt axis 1.
- `position_ids` is sliced on its last axis so mRoPE shapes such as
  `[batch, 3, seq]` remain valid.
- Other known prompt-length-aware kwargs with second-axis sequence shape keep
  the existing second-axis behavior.
- Slice windows use normalized `cache_offset` and `seq_len` values.
- If the backend already provides a tensor whose prompt axis is exactly
  `seq_len`, Melix treats it as pre-sliced for the current chunk and passes it
  through without recording a fallback.
- If a tensor cannot cover the requested slice window, Melix records a
  `multimodal_position_slice_fallback_count` receipt value instead of silently
  claiming aligned chunking.

## Performance Probes And Success Metrics

- Regression fixtures prove that chunked `inputs_embeds` and at least one
  prompt-length-aware kwarg stay aligned for the same chunk window.
- Regression fixtures prove that `position_ids` uses
  `cache_offset:cache_offset + seq_len`, including mRoPE last-axis slicing.
- Regression fixtures prove that already aligned decode-time auxiliary tensors
  do not increment fallback diagnostics.
- Long-video and repeated-media fixtures expose
  `multimodal_position_slice_fallback_count` through the existing VLM probe
  snapshot path.
- This slice does not claim throughput improvement. Success is correctness and
  diagnostics before enabling broader fast-path promotion.

## Implementation Steps

1. Add failing tests in `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
   for chunked auxiliary tensor slicing:
   - aligned `inputs_embeds` and `position_ids` slices for `cache_offset=4` and
     `seq_len=2`;
   - fallback count when a requested chunk window extends beyond the available
     position metadata.
2. Add a small helper in
   `services/mlx-worker-python/worker/runtime/mlx_vlm_runtime.py` that returns a
   sliced kwargs dict plus a fallback count.
3. Thread the fallback count into `VisionProbeSnapshot` and receipts as
   `multimodal_position_slice_fallback_count`.
4. Extend deterministic VLM probe defaults only as needed so existing evidence
   serialization can read the new probe attribute consistently.
5. Run focused Python tests, then changed-scope coverage and the repository
   verification gate before PR handoff.

## Verification

Required focused checks before PR handoff:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_mlx_vlm_runtime.py services/mlx-worker-python/tests/test_multimodal_position_receipts.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_vision_runtime.py::test_vlm_generate_records_attention_policy_before_first_token`
- Changed-line coverage for touched Python files must be at least 95 percent.

## Non-Goals

- No protobuf schema change.
- No dependency bump for `mlx-vlm`.
- No streaming versus non-streaming parity fixture; issue #1452 owns that work.
- No live performance speedup claim.
