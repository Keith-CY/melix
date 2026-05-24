# Issue 1531 Training Planner Receipts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add durable advanced training planner, backend, profiler, and numerical-policy receipt fields for SFT/QLoRA training runs.

**Architecture:** The Python worker remains the execution truth. `normalize_training_config` resolves a small, typed planner receipt from already-normalized training config inputs and request extensions, and the LoRA training manifest persists that receipt without revalidating admission rules already owned by existing training-mode and adapter-capability checks. Reward-model and RL-specific smoke promotion stays out of this slice because #366 only blocks those smoke promotions, not SFT/QLoRA receipt work.

**Tech Stack:** Python dataclasses, existing worker model-ops normalization, pytest focused worker tests.

---

### Task 1: Planner Receipt Contract

**Files:**
- Modify: `services/mlx-worker-python/worker/model_ops/training_config.py`
- Test: `services/mlx-worker-python/tests/test_training_planner_receipts.py`

- [ ] **Step 1: Write failing tests**

Add tests that normalize SFT and QLoRA configs and assert `training_planner_receipt` contains `batching_strategy`, `cutoff_len`, `micro_batch_size`, `effective_token_budget`, `packing_mode`, `media_counts`, `kernel_policy`, `expected_peak_memory_class`, `profile_artifact_path`, `compiled_step_enabled`, `grad_checkpoint_enabled`, `attention_backend`, `metric_for_best_model_resolved`, `generation_mode`, and `final_logit_softcapping`.

- [ ] **Step 2: Run RED verification**

Run:

```bash
PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_training_planner_receipts.py -q
```

Expected: fails because `LoRATrainingConfig.training_planner_receipt` does not exist.

- [ ] **Step 3: Implement the receipt**

Add a `training_planner_receipt` field to `LoRATrainingConfig`, resolve it after config scalars are normalized, and keep it informational. Unsupported attention backends produce a typed refusal receipt instead of blocking unrelated planner/backend/profiler work.

- [ ] **Step 4: Run GREEN verification**

Run the same pytest command and expect pass.

### Task 2: Adapter Manifest Persistence

**Files:**
- Modify: `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`
- Test: `services/mlx-worker-python/tests/test_training_planner_receipts.py`

- [ ] **Step 1: Write failing manifest test**

Use the existing `LoRATrainingPipeline` deterministic runner pattern to train a tiny local SFT fixture and assert the generated `train_lora.adapter.json` persists every planner receipt field.

- [ ] **Step 2: Run RED verification**

Run:

```bash
PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_training_planner_receipts.py -q
```

Expected: fails because the manifest does not yet include the planner receipt fields.

- [ ] **Step 3: Persist receipt fields**

Merge `config.training_planner_receipt` into the adapter manifest near existing training config and metrics fields.

- [ ] **Step 4: Run GREEN verification**

Run the same pytest command and expect pass.

### Task 3: Focused Regression Checks

**Files:**
- Test: `services/mlx-worker-python/tests/test_lora_model_ops_unit.py`
- Test: `services/mlx-worker-python/tests/test_agentic_sft_training_contract.py`

- [ ] **Step 1: Run focused existing tests**

Run:

```bash
PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_training_planner_receipts.py services/mlx-worker-python/tests/test_agentic_sft_training_contract.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py -k "training_config or planner_receipt or chunked_training or candidate_generation_mode" -q
git diff --check
```

Expected: pass. This confirms the new receipt fields do not alter admission validation, agentic SFT contracts, chunked-training config, or generation-mode safety.

## Performance Probes And Metrics

This slice adds constant-size receipt construction and manifest JSON fields on the training setup path. It does not change the native training loop, dataset chunking loop, or MLX execution kernels. Success metrics are:

- `training_planner_receipt_field_count`: 15 required receipt fields present.
- `attention_backend.status`: `accepted` or `refused` with a stable reason.
- `profile_artifact_path`: empty when no profiler artifact exists, or a configured path when supplied.

No PR-scoped runtime performance probe is required for this focused receipt-only slice.

## 2026-05-24 Review Follow-Up

`expected_peak_memory_class` also accounts for source-model size metadata when
available. Resident-byte metadata is evaluated before parameter-count metadata,
then the original effective-token-budget heuristic remains the fallback for
models without size hints.
