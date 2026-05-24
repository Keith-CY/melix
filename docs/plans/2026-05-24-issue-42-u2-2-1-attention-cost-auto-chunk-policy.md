# Issue 42 U2.2.1 Attention-Cost Auto-Chunk Policy

## Source

- GitHub issue: <https://github.com/Keith-CY/melix/issues/1450>
- Parent plan: <https://github.com/Keith-CY/melix/issues/1430>
- Governing roadmap: `docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md`

## Goal

Add a worker-local admission policy that predicts media-expanded attention
bytes before VLM prefill or generation starts, then records whether the request
can run whole, should use a conservative prefill chunk size, or must be refused.

## Architecture

The policy belongs in the Python worker VLM runtime because the worker owns
execution truth, media-expanded prompt token counts, and the first forward-pass
boundary. `vision_family_adapters` keeps family metadata and token counting;
the new policy helper consumes the resolved family, prepared request, prompt
tokens, execution metadata, and optional loaded-model metadata. Runtime probe
snapshots then carry the policy receipt beside existing multimodal fast-path and
position metadata receipts.

This slice does not implement chunked tensor slicing. It only selects and
records a conservative `prefill_step_size` for verified families, or returns a
typed refusal when the predicted attention cost is above the active budget and
no safe chunk is available. Follow-up units #1451 and #1452 own auxiliary tensor
slicing and streaming/non-streaming parity fixtures.

## Policy Inputs

- `prompt_tokens`: media-expanded prompt token count from the resolved vision
  family.
- `vision_family_id`: resolved family id.
- `max_context`: model max context when available.
- `attention_cost_budget_bytes`: optional model or execution metadata override.
- `prefill_step_size`: request-level prefill step size, used as an existing
  upper bound when present.
- `hidden_size`, `num_hidden_layers`, and `attention_dtype_bytes`: optional
  metadata used for a conservative byte estimate.

## Policy Outputs

Each VLM probe receipt includes:

- `attention_budget_verified_family`
- `attention_budget_family_id`
- `attention_budget_prompt_tokens`
- `predicted_attention_bytes`
- `attention_budget_bytes`
- `prefill_chunk_mode`
- `selected_prefill_step_size`
- `auto_chunk_reason`
- `attention_budget_refusal_count`

## Behavior

- Verified families with predicted cost inside budget use
  `prefill_chunk_mode=whole_prefill`.
- Verified families above budget select a conservative chunk size when chunking
  is possible, recording `auto_chunk_reason=attention_budget_auto_chunked`.
- Verified families above budget refuse before forward pass when even the
  minimum supported chunk is over budget, recording
  `auto_chunk_reason=attention_budget_exceeded`.
- Unverified families record the conservative predicted cost but do not enforce
  budget decisions from an unverified adapter family. They record
  `prefill_chunk_mode=family_unverified` and
  `auto_chunk_reason=unverified_family_opt_out`.

## Performance Probes And Success Metrics

- Unit tests must prove `predicted_attention_bytes` is computed before backend
  generation or prefill-side session creation.
- Unit tests must cover whole-prefill, auto-chunk, typed refusal, and
  unverified-family fallback receipts.
- Metrics scope is evidence mode only for this slice. No new protobuf
  `RuntimeStats` fields are added.

## Verification

Required focused checks before PR handoff:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_multimodal_attention_policy.py services/mlx-worker-python/tests/test_vision_runtime.py::test_vlm_prefill_rejects_over_budget_attention_before_decode_session services/mlx-worker-python/tests/test_vision_runtime.py::test_vlm_generate_rejects_over_budget_attention_before_first_token services/mlx-worker-python/tests/test_vision_runtime.py::test_vlm_generate_records_attention_policy_before_first_token`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_multimodal_position_receipts.py services/mlx-worker-python/tests/test_multimodal_fast_paths.py`
- Changed-line coverage for touched Python files must be at least 95 percent.

## Non-Goals

- No protobuf schema change.
- No live throughput claim.
- No auxiliary tensor slicing.
- No streaming versus non-streaming parity claim.
