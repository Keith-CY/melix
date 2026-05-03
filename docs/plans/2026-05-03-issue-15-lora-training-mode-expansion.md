# Issue 15 LoRA Training Mode Expansion

## Goal

Expand the Melix LoRA training contract beyond LoRA and QLoRA SFT by adding
product-owned boundaries for DoRA, preference-tuning datasets and modes, and
continual-pretraining datasets and mode behavior.

## Source

- GitHub issue: https://github.com/Keith-CY/melix/issues/15
- Governing roadmap: `docs/plans/2026-04-16-lora-capability-modules-and-commit-plan.md`
- Operator runbook: `docs/runbooks/phase-8-lora-adapter-workflow.md`

## Scope

- Treat `training_mode=dora` as a first-class adapter training contract with
  validation and manifest evidence.
- Add preference-pair dataset contracts for preference-style modes.
- Add `training_mode=dpo` and `training_mode=orpo` as preference-mode
  boundaries that validate preference-pair datasets and preserve manifest
  evidence without claiming full trainer execution breadth beyond the current
  local runner.
- Add `training_mode=cpt` as a continual-pretraining boundary that requires
  text-only datasets and disables response-only SFT assumptions.
- Keep existing `lora` and `qlora` SFT behavior unchanged.

## Non-Goals

- Implement full DPO, ORPO, or CPT optimizer loops in MLX-LM.
- Add UI or CLI surface changes outside the worker-owned operation contract.
- Add QAT forward hooks from the later issue comments; those comments define a
  follow-up direction but are larger than Module 4's requested contract slice.

## Implementation Plan

- [x] Sync `main` to `origin/main` and create an isolated worktree.
- [x] Verify baseline targeted LoRA tests on the synced branch.
- [x] Extend `LoRATrainingConfig` with training objective and adapter algorithm
  metadata.
- [x] Add DoRA mode normalization and persist DoRA manifest fields.
- [x] Add preference-pair dataset format validation and normalization.
- [x] Add DPO/ORPO mode validation against preference-pair datasets.
- [x] Add CPT mode validation against text-completion datasets.
- [x] Update LoRA runbook examples and operator expectations.
- [x] Run targeted pytest and `git diff --check`.

## Performance And Metrics

- No new long-running trainer loop is introduced in this slice.
- Dataset validation remains pre-runner and bounded by existing package sample
  normalization.
- Success metrics:
  - DoRA manifests expose `adapter_algorithm=dora`.
  - DPO and ORPO requests require `preference_pair` datasets and record
    `training_objective=preference`.
  - CPT requests require `text_completion` datasets and record
    `training_objective=continual_pretraining`.
  - Existing LoRA/QLoRA SFT regression tests continue to pass.

## Verification

- `make bootstrap`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_lora_model_ops.py -q`
- `make py-coverage`
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue15-python-coverage.json services/mlx-worker-python/worker/model_ops/training_config.py services/mlx-worker-python/worker/model_ops/training_dataset.py services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`
- `git diff --check`

## Baseline Evidence

- `make bootstrap`: passed on the isolated worktree.
- Targeted pytest before changes: `66 passed in 2.46s`.

## Implementation Evidence

- Targeted pytest after changes:
  `78 passed in 7.05s`.
- Related runner/config regression tests:
  `81 passed in 0.55s`.
- `make py-coverage`:
  `1537 passed, 5 skipped, 2 warnings in 171.48s`; repository Python
  coverage remained `95%`.
- Python changed-line coverage for touched worker files:
  `100.00% (58/58)`.
- `git diff --check`: passed.
