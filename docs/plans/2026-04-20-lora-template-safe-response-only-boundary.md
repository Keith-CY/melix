# Milestone #43 · Phase 2 — Template-aware response-only boundary observability

## Context

Issue [#43](https://github.com/Keith-CY/melix/issues/43) Phase 2 is scoped in the milestone as:

> - template-derived assistant and completion masking instead of brittle token heuristics
> - add cross-family fixtures that prove response-only masking remains correct
> - keep response-only loss masking correctness at 100 percent on the supported chat-template fixture matrix

A code read on `main @ f63df78f` updates a load-bearing assumption of the issue text: Melix does **not** do hardcoded token heuristics today. Response-only masking is fully delegated to MLX-LM's `ChatDataset.process()` (`.venv/.../mlx_lm/tuner/datasets.py:39–84`), which renders the chat template and derives an accurate prompt-boundary offset at training time. The actual Phase 2 gaps are:

1. **Observability** — the boundary is recomputed inside MLX-LM every epoch; Melix doesn't see, log, or persist it. Operators cannot inspect which tokens get masked.
2. **Cross-family evidence** — the only training fixture is `fixtures/training/melix-dev-dataset.v1` (2 generic samples). There is no matrix that proves masking is correct across Llama/ChatML/Mistral/Gemma-style templates.

Phase 1 (PR #45) shipped `gradient_accumulation` + resume surface. Phase 2 is the first correctness-adjacent slice.

## Scope

**In:** compute the response-only boundary on the Melix side at dataset-normalization time (reusing `tokenizer.apply_chat_template`), persist boundary metadata per sample plus aggregate stats in the training manifest, and commit a chat-template fixture matrix whose boundaries are asserted against an MLX-LM-compatible reference computation.

**Out:** training real LoRA adapters on each family (requires GB-scale downloads + long runs), Phase 3 long-context chunked training, Phase 4 alignment candidate scoring, and any change to MLX-LM's internal `ChatDataset` contract.

## Slices

### 2A — Boundary helper + normalization wire-in

- Add `compute_response_only_boundary(messages, tokenizer) -> dict` in `worker/model_ops/training_dataset.py`:
  - `tokenizer.apply_chat_template(messages, add_generation_prompt=False)` → full tokens.
  - `tokenizer.apply_chat_template(messages[:-1], add_generation_prompt=True)` → prefix tokens.
  - Return `{assistant_offset, total_tokens, response_tokens}` (no full token list in the persisted record — only the boundary metadata).
- Call site: sample normalization for `format == "chat_messages"`. Boundary is attached to the normalized-sample record as `response_only_boundary`.

### 2B — Manifest persistence

In `worker/model_ops/lora_training_pipeline.py`, when `config.response_only` is true and samples carry boundary metadata, compute and surface:

- `response_only_boundary_min`
- `response_only_boundary_max`
- `response_only_boundary_mean`
- `response_only_boundary_sample_count`

These let an operator confirm that masking did affect an expected range of each sample.

### 2C — Cross-template fixture matrix + validation tests

New fixture `fixtures/training/chat-template-matrix.v1/`:

- `manifest.json` — schema `melix.dataset.chat_template_matrix.v1`, enumerates four template families.
- `samples.jsonl` — 5 samples per family; variations cover 1-turn / multi-turn, system / no-system, short / long user turn.
- `expected_boundaries.jsonl` — committed expected `{family, sample_index, assistant_offset, total_tokens}`.
- `templates.json` — Jinja chat template per family, drawn from public upstream `tokenizer_config.json` `chat_template` fields.

New test `tests/test_response_only_boundary.py`:

- Per family × sample, load a base tokenizer, override `chat_template`, call `compute_response_only_boundary`, assert the result matches the committed expected entry.
- Parity test with MLX-LM's `ChatDataset.process()` — the offsets MUST match bit-for-bit across the matrix plus the existing `melix-dev-dataset.v1` samples.

The 100% correctness claim is operationalized as: bit-exact offset equality between Melix's new helper and MLX-LM's existing computation, across all committed fixtures.

### 2D — Regression guardrails

- MLX-LM integration is unchanged (still passes `mask_prompt=config.mask_prompt`).
- Missing `response_only_boundary` on older normalized datasets is safe — MLX-LM recomputes at training time. Melix's field is additive observability.
- Manifest schema stays `melix.lora_adapter_package.v1`; new fields are additive.

## Critical files

```
services/mlx-worker-python/worker/model_ops/training_dataset.py
services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py
services/mlx-worker-python/tests/test_response_only_boundary.py
services/mlx-worker-python/tests/test_lora_model_ops.py
services/mlx-worker-python/fixtures/training/chat-template-matrix.v1/
```

## Verification

Run in order:

1. `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_response_only_boundary.py -v`
2. `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops_unit.py -q`
3. `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops.py -q`
4. `make py-test`

Optional: `MELIX_PHASE8_REAL_SMALL_MODEL_E2E=1 make phase8-real-e2e` — Phase 2 changes are additive so this must stay green.

## Evidence

- New-test count + baseline count in the touched Python test suites.
- Manifest-delta snippet showing the four new aggregate fields on the existing `melix-dev-dataset.v1`.
- `pytest -k response_only_boundary -v` output with all 4 families × 5 samples passing.
- Explicit statement that Phase 2 does not change masking semantics — it surfaces the same boundary MLX-LM already computes and pins it to a cross-family evidence matrix. Phase 3+ can consume the persisted boundary for long-context chunked training.

## Out of scope

- Training real LoRA adapters on Llama / Mistral / Gemma.
- Phase 3 chunked backend, Phase 4 alignment candidate scoring.
- Replacing MLX-LM's internal offset computation.

## Risks

- Jinja template rendering may diverge subtly from upstream tokenizers; mitigation — copy `chat_template` verbatim from upstream `tokenizer_config.json` and document the source.
- Cross-family test needs a base tokenizer; use the locally cached `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` tokenizer that is already on disk from the PR #45 verification. Fall back to `pytest.mark.skip` when the cache is missing (matches the `MELIX_PHASE8_REAL_SMALL_MODEL_E2E` gating pattern).
- Aggregate-stats fields add to the manifest shape but are additive; existing consumers use `.get()` so they stay compatible.
