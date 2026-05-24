# Issue 1529 LoRA Canary Receipts Implementation Plan

## Goal

Add focused LoRA artifact, resume, merge/export, callback drift, and
teacher-forced canary receipts without changing admission validators or generic
export gates.

## Governing Sources

- `AGENTS.md`
- `docs/runbooks/phase-8-lora-adapter-workflow.md`
- GitHub issue #1529
- `docs/plans/2026-05-24-closed-issue-post-closure-followup-audit.md`

## Scope

This slice is worker-local and records canary evidence on LoRA training
artifacts. It does not modify the closed-issue follow-up coordinator plan, open
or close GitHub issues, change dependency gates, or add training admission
validators.

## Architecture

Add a small metadata helper beside the existing LoRA runtime metadata helpers.
The training pipeline will call it after adapter weights and config are written,
then copy the resulting receipt fields into `train_lora.adapter.json`.
`LoraExperimentStore` will preserve the same receipt values in per-run records
so run history can surface drift evidence without reparsing adapter manifests.

## Success Metrics

- Focused LoRA metadata/model-op pytest canaries pass.
- `git diff --check` passes.
- Receipt fields are present on successful deterministic LoRA runs:
  `source_eos_token`, `saved_eos_token`, `tokenizer_config_path`,
  `base_config_present`, `processor_resume_mode`, `aux_modules_restored`,
  `merge_export_canary_result`, `callback_api_drift_result`,
  `completion_loss`, `round_trip_passed`, and `grad_norm`.

## TDD Steps

1. Add a failing unit test for artifact/resume canary metadata using a temporary
   base model directory with config, tokenizer, processor, and auxiliary module
   fixtures.
2. Add a failing pipeline test proving `train_lora.adapter.json` records all
   expected receipt fields for deterministic training.
3. Add a failing checkpoint canary test for missing base config/tokenizer/aux
   state.
4. Implement the smallest helper and manifest wiring needed to pass those
   tests.
5. Add experiment-store assertions if the manifest fields are not already
   visible from run records.
6. Run focused pytest filters and `git diff --check`.
