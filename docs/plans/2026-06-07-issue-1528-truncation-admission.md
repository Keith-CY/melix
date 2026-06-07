# Issue 1528 Truncation Admission Implementation Plan

## Goal

Fail LoRA training requests before backend execution when sequence truncation
would remove required supervision tokens, and emit stable typed evidence for
operators to correct the request.

## Architecture

The Python worker keeps training admission in the worker-owned model operation
path because CLI, API, and Desktop all converge there before backend training.
This slice extends the existing response-only boundary probe with a stable
422-style error shape and adds a lightweight normalized-dataset inspection for
media-token truncation requests. It does not change MLX-LM training semantics
or preference loss math; preference loss already uses safe token counts for
fully masked rows.

## Scope Boundaries

- Include: response-only zero-label failures with `field`, `reason`,
  sample/count, requested/effective sequence length, and corrective action.
- Include: media-token truncation admission for normalized chat samples whose
  declared media-token budget cannot fit inside `max_seq_length`.
- Include: preservation of chat sample media references and media-token hints
  in the normalized dataset snapshot.
- Include: runner/service tests proving invalid requests fail before
  `train_model`.
- Include: runbook documentation for the new typed error details.
- Exclude: real VLM processor tokenization, image/video decoding, or model
  family-specific media feature packing.
- Exclude: changing DPO/ORPO/CPO reducers; their zero-token guard is already
  covered by safe token counts.

## Files

- Modify: `services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py`
  - Upgrade `_validate_response_only_trainable_tokens` details to the stable
    watch-log schema.
  - Add a pre-`load_local_dataset` normalized `train.jsonl` media truncation
    admission pass.
- Modify: `services/mlx-worker-python/worker/model_ops/training_dataset.py`
  - Preserve structured `media_refs` and media-token hint fields from
    `chat_messages` samples so admission checks can use package metadata.
- Modify: `services/mlx-worker-python/tests/test_lora_model_ops_unit.py`
  - Update the existing zero-label test to assert the stable schema.
  - Add a media-token truncation test that proves `train_model` is not called.
  - Add normalization coverage for preserving media-token hints.
- Modify: `services/mlx-worker-python/tests/test_lora_model_ops.py`
  - Add service-level coverage proving typed admission details survive the
    shared worker `ConvertModel(train_lora)` failure event.
- Modify: `docs/runbooks/phase-8-lora-adapter-workflow.md`
  - Document `no_unmasked_completion_tokens` and `media_tokens_truncated`
    training admission failures.

## Test Plan

1. Add failing assertions for the new zero-label error shape.
2. Add a failing media-token truncation test with a fake MLX-LM module.
3. Run the focused tests and verify they fail for missing fields/behavior.
4. Implement the minimal runner admission helpers.
5. Re-run focused tests:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py -k "normalize_sample_covers_prompt_text_and_tool_paths or response_only_labels_are_truncated or media_tokens"
```

6. Run a service-level typed error propagation test:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py -k "admission_failure_preserves_typed_error_details"
```

7. Run changed-scope coverage and `git diff --check`.
8. Before commit, run the repository pre-commit hook through `git commit`,
   which executes `make swift-test`, `make py-test`, `make integration-test`,
   and the scoped performance report on this host.

## Performance Probes And Metrics

The response-only validation uses an aggregate already computed from MLX-LM's
train set, so the change is error-detail only. The media truncation scan reads
normalized `train.jsonl` once before backend training and only performs integer
accounting over top-level sample metadata. Success metric: invalid fixtures
return typed admission errors before `train_model`, changed-line coverage is at
least 95%, and the PR-scoped performance report has zero regressions.
