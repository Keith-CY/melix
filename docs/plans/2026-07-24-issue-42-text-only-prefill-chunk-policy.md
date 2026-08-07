# Issue 42 Text-Only Prefill Chunk Policy

## Source

- GitHub issue: <https://github.com/Keith-CY/melix/issues/42>
- Watch note (2026-07-24): "bound long text-only prefill inside the multimodal lane"
- Governing roadmap: `docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md`
- Related slice: `docs/plans/2026-05-24-issue-42-u2-2-1-attention-cost-auto-chunk-policy.md`

## Goal

Add a worker-local admission policy that decides whether a text-backed VLM/MTP
request can prefill its prompt prefix in bounded chunks instead of one
full-sequence forward, then records a machine-readable receipt describing the
decision. The policy resolves an effective prefill step size (the current
text-backed path passes `prefill_step_size=None`) and stays fail-safe: any
condition that would make chunking incorrect keeps the original single-forward
path.

## Architecture

The policy belongs in the Python worker VLM runtime, alongside the existing
attention-cost auto-chunk policy. It performs no model forward work — it only
resolves an effective step size, applies correctness guards, and produces a
receipt. This keeps the decision cheap and unit-testable without an Apple
Silicon backend. Runtime probe snapshots carry the new
`text_prefill_chunk_receipt` beside the existing attention-budget, position
metadata, and multimodal fast-path receipts.

This slice owns the decision and its receipt only. Materializing prefix-only
cache state between chunks and running the final token separately in the real
`mlx-vlm`/native-MTP decode loop is follow-up work gated on this policy.

Only `has_media` is observable at the probe-recording sites. The partial-mask,
cache-presence, and sequence-aligned-extra-input guards are decode-loop facts
that do not exist before the first forward, so the configured resolver applies
its eligible defaults at those sites while still forwarding every guard through
to `resolve_text_prefill_chunk_policy`. The follow-up that lets this decision
drive chunked execution must pass the observed signals through
`resolve_configured_text_prefill_chunk_policy`; until then the receipt reports
`chunked_prefix` for eligible long text-only prompts based on media and length
alone.

## Policy Inputs

- `prompt_tokens`: resolved prompt token count.
- `requested_prefill_step_size`: request/metadata step size, `None` when unset.
- `has_media`: whether the resolved request carries any image or video input.
- `has_sequence_aligned_extra_inputs`: whether unknown sequence-aligned inputs
  are present.
- `attention_mask_all_valid`: whether the mask is absent or all-valid.
- `cache_present`: whether the language-model KV cache is available for reuse.

Configuration is opt-in through `melix.vlm.text_prefill_step_size` (or
`melix.vlm.text_prefill_chunk_tokens`) in model metadata or execution ext,
mirroring the attention-budget policy's opt-in shape. When unset, the receipt is
empty and default behavior is unchanged.

## Policy Outputs

Each configured text-backed VLM probe receipt includes:

- `prefill_mode` — `single_forward` or `chunked_prefix`
- `prompt_tokens`
- `effective_prefill_step_size`
- `prefill_chunk_tokens`
- `prefix_chunks`
- `final_logits_positions`
- `fallback_reason`

## Behavior

- Media inputs, sequence-aligned extra inputs, a partial attention mask, or a
  missing cache each force `prefill_mode=single_forward` with a typed
  `fallback_reason` (`media_present`, `sequence_aligned_extra_inputs`,
  `partial_attention_mask`, `cache_unavailable`).
- A prompt whose prefix fits inside a single step keeps
  `prefill_mode=single_forward` with `fallback_reason=prompt_within_single_chunk`
  so ordinary short-prompt latency is unchanged.
- An eligible prompt whose prefix crosses at least one chunk boundary selects
  `prefill_mode=chunked_prefix`, chunking `prompt_tokens - 1` prefix tokens into
  `prefix_chunks` forwards of `prefill_chunk_tokens` each and running the final
  token separately, so only one `[batch, 1, vocab]` projection is needed
  (`final_logits_positions=1`).
- An unset step size resolves to the VLM text-only batch default (512), clamped
  to `[1, 8192]`.

## Performance Probes And Success Metrics

- Unit tests cover chunked prefix, single-chunk single-forward, all four guard
  fallbacks, guard precedence, step-size normalization, and the receipt shape.
- Deterministic runtime tests prove the probe records a `chunked_prefix` receipt
  for a text-only request and a `media_present` receipt for an image request,
  and stays empty when unconfigured.
- Metrics scope is evidence mode only for this slice. No new protobuf
  `RuntimeStats` fields are added.

## Verification

Required focused checks before PR handoff:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python --group dev pytest -q services/mlx-worker-python/tests/test_text_prefill_chunk_policy.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python --group dev pytest -q services/mlx-worker-python/tests/test_multimodal_attention_policy.py services/mlx-worker-python/tests/test_deterministic_vlm_probe_snapshot.py services/mlx-worker-python/tests/test_multimodal_fast_paths.py`

## Non-Goals

- No protobuf schema change.
- No live throughput or peak-memory claim (the real chunked decode loop and its
  Apple Silicon memory/TTFT probe are follow-up work).
- No change to the public multimodal API shape.
- No change to default behavior when the step size is unconfigured.
