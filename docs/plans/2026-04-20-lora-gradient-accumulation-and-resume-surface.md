# Milestone #43 · Phase 1 — Gradient Accumulation & Resume Surface

## Context

Issue [#43](https://github.com/Keith-CY/melix/issues/43) is a four-phase milestone for long-context and advanced fine-tuning. Phase 1 is the only slice that ships cleanly today: expose `gradient_accumulation` and `resume` controls through the operator surface and make them observable in the training manifest.

The issue's Phase 1 explicit target is operator visibility, not throughput or memory:

> expose gradient accumulation, resume status, and long-context mode in training manifests and operator-visible receipts

Current state (verified via code read on `main @ 823082af`):

- `LoRATrainingConfig` (`services/mlx-worker-python/worker/model_ops/training_config.py`) has `response_only`, `gradient_checkpointing`, `mask_prompt`, `max_seq_length`, etc. but **no `gradient_accumulation` field**.
- `mlx_lm_runner._mlx_lora_namespace()` hardcodes `grad_accumulation_steps=1` (runner.py line ~289).
- `resume_source_path` is threaded through `ext → config → TrainingRequest → MLX-LM resume_adapter_file` and surfaces in the manifest, but **the CLI has no flag**. Operators cannot trigger resume without passing raw `ext` values.
- Training manifest schema is `melix.lora_adapter_package.v1` (`lora_training_pipeline.py:130-225`) and already carries `tokens_per_second`, `peak_memory_gb`, `checkpoint_count`, `latest_checkpoint_path`, `resume_ready`, `resume_source_path`, `resume_source_job_id`.

Phases 2 (template-safe masking), 3 (long-context chunked backend), and 4 (batched candidate scoring for alignment) are out of scope for this plan.

## Slices

### 1A — `gradient_accumulation` config / wire / manifest

- `training_config.py`: add `gradient_accumulation: int` to `LoRATrainingConfig` (default `1`); normalize in `normalize_training_config()` with `>= 1` validation (reuse `_int_value` style helper).
- `mlx_lm_runner.py`: replace hardcoded `grad_accumulation_steps=1` with `request.config.gradient_accumulation` in `_mlx_lora_namespace()`.
- `lora_training_pipeline.py`: surface three fields in the manifest next to `training.batch_size`:
  - `gradient_accumulation`
  - `effective_batch_size` = `batch_size * gradient_accumulation`
  - `optimizer_steps` = `iters // gradient_accumulation` (floor; for operator observability)

### 1B — Resume CLI surface

- `Sources/MelixCLICore/MelixCLI.swift`:
  - Add `--resume-adapter PATH` on `lora train` → `parameters["resume_source_path"]`.
  - Add `--resume-from-manifest PATH` → `parameters["resume_manifest_path"]`.
  - Update usage text and `MelixCLICommandCodec.arguments(for:)` mapping.
- Python worker: no changes needed — `_resolve_resume_context` already handles both ext keys.

### 1C — Observability & quantification harness

The "prove the plumbing works" guard the scope requires.

- **Python unit tests** (`tests/test_lora_model_ops_unit.py`):
  - `gradient_accumulation` normalization: accept positive int, reject `0` / negative / non-numeric strings.
  - `_mlx_lora_namespace` returns `grad_accumulation_steps == config.gradient_accumulation`.
  - Manifest shape: `gradient_accumulation`, `effective_batch_size`, `optimizer_steps` present with expected values.
- **Swift parser test** (`tests/MelixCLITests/MelixCLIParserTests.swift`):
  - `melix lora train ... --gradient-accumulation 4 --resume-adapter /tmp/x` round-trips to `parameters["gradient_accumulation"] == "4"` and `parameters["resume_source_path"] == "/tmp/x"`.
- **Integration plumbing** (`tests/test_lora_model_ops.py` extension):
  - Run the existing `melix-dev-dataset.v1` fixture with `gradient_accumulation=1` and `gradient_accumulation=2`, capture both manifests, assert the new fields are present and consistent.
  - This deliberately does **not** assert throughput or convergence improvements: MLX-LM's honoring of the flag is the library's contract, out of Phase 1 scope. A FIXME comment documents that boundary.

## Critical files

```
services/mlx-worker-python/worker/model_ops/training_config.py
services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py
services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py
services/mlx-worker-python/tests/test_lora_model_ops_unit.py
services/mlx-worker-python/tests/test_lora_model_ops.py
Sources/MelixCLICore/MelixCLI.swift
tests/MelixCLITests/MelixCLIParserTests.swift
```

## Verification

Run in order; stop on first failure.

1. `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops_unit.py -q`
2. `xcrun swift test --filter MelixCLIParserTests`
3. `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_lora_model_ops.py -q`
4. `xcrun swift test --filter MelixCLI`
5. `make py-test`
6. Optional sanity: `MELIX_PHASE8_REAL_SMALL_MODEL_E2E=1 MELIX_PHASE8_REAL_SMALL_MODEL_PATH=... make phase8-real-e2e` — phase8 bundle does not use grad_accum, so it should be unaffected.

## Evidence to report

Per AGENTS.md metrics rules, the PR body must include:

- Counts of new / modified unit tests, all passing.
- `pytest -k lora -q` result.
- `xcrun swift test --filter MelixCLI` result.
- Baseline vs grad_accum=2 manifest snippets showing the three new fields populated correctly (demonstrates plumbing, not throughput).

## Out of scope

- Phase 2 (template-safe masking)
- Phase 3 (long-context chunked backend, 4k/8k smoke, 25% throughput / 30% memory gates)
- Phase 4 (batched candidate scoring)
- MLX-LM backend correctness of `grad_accumulation_steps`
- Issue #14 experiment lifecycle surfaces (orthogonal: this plan only enables a single resume CLI trigger, not experiment grouping)

## Risks

- MLX-LM may silently ignore `grad_accumulation_steps` — mitigation: test comment documents the plumbing-only scope; an observed behavioral discrepancy becomes a follow-up issue.
- Operator confusion between `--resume-adapter` and `--resume-from-manifest` — mitigation: usage text + at most one recommended flag per scenario.
