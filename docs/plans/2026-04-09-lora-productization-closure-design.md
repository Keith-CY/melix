# LoRA Productization Closure Design

## Purpose

Close the remaining LoRA product gaps in Melix so training, activation, lifecycle management,
evaluation comparison, and acceptance evidence all behave as one product surface across the
Python worker, Swift control plane, CLI, and Window UI.

## Fixed Acceptance Baseline

All LoRA-related acceptance, smoke, and end-to-end evidence in this closure uses the same small
base model:

- `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`

This baseline applies to:

- LoRA train and activate acceptance
- QLoRA train and activate acceptance
- derived-model lifecycle acceptance
- LoRA-versus-base evaluation comparison acceptance
- CLI acceptance evidence
- Window UI acceptance evidence

The product may still support other models, but acceptance evidence for this closure is anchored to
one deterministic baseline so operator runbooks, fixtures, and release gates do not drift.

## Current Gaps

As of 2026-04-09, the LoRA stack is only partially closed:

- real LoRA training and fused activation already exist
- Hugging Face dataset ingestion exists, but `hf_valid_split` is not productized end to end
- activation accepts `adapter_backed_runtime` in shape only; serving and catalog behavior are not
  closed
- there is no first-class `remove_derived_model` lifecycle surface
- LoRA comparison is still a manual evaluation workflow rather than a product path
- acceptance docs still describe live validation as pending
- repository docs and acceptance harnesses do not consistently pin the base model to
  `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`

## Product Goals

### Goal 1: Complete the training matrix

Melix must support both `lora` and `qlora` as real training modes on the same operator surface.
Both modes must share the same dataset packaging, progress stages, manifest contracts, and publish
flow, with mode-specific backend configuration preserved in stored artifacts.

### Goal 2: Complete the derived-model lifecycle

Melix must expose the full lifecycle for adapter-derived models:

- activate as `fused_derived_model`
- activate as `adapter_backed_runtime`
- register derived models into the catalog
- remove derived models through a product-owned operation
- preserve adapter-aware cache identity in all runtime paths

### Goal 3: Make LoRA comparison first-class

Melix must provide one evaluation workflow that compares a base model and one or more activated
derived models under the same suite, controls, and sample ordering. The output must persist deltas,
paired sample rows, regression counts, and exportable reports.

### Goal 4: Close acceptance and evidence

Every LoRA closure feature must have:

- positive and negative unit coverage
- CLI end-to-end coverage
- Window UI end-to-end or smoke coverage
- updated English runbooks
- refreshed acceptance evidence tied to the fixed Qwen acceptance model

## Scope

### Included

- QLoRA implementation in the worker runner and training manifests
- validation split materialization for Hugging Face datasets
- training-side desired derived-model alias propagation
- activation-mode productization for `adapter_backed_runtime`
- derived-model removal as an internal model operation without adding new public RPC surfaces
- catalog, registry snapshot, CLI, and Window UI support for the new lifecycle states
- evaluation compare jobs and persisted exports for base-versus-derived LoRA analysis
- release and acceptance runbook refresh with the fixed acceptance model

### Excluded

- new public protobuf RPC surfaces
- distributed or cloud LoRA training
- new multimodal LoRA training modes
- changing the benchmark or evaluation product away from serial local execution in v1
- replacing the broader model-library default model bootstrap outside the touched LoRA acceptance
  scope

## Product Decisions

### Training mode behavior

- `training_mode=lora` remains the default.
- `training_mode=qlora` becomes a supported mode rather than a reserved failure.
- QLoRA uses the same public `train_lora` operation and adapter package schema, with manifests
  recording quantization-aware training metadata.
- Unsupported base families, quantization combinations, or backend dependency gaps fail with typed
  errors rather than falling back silently.

### Validation split behavior

- `hf_valid_split` becomes an optional first-class input for Hugging Face datasets.
- When provided, Melix materializes both train and validation snapshots and passes them to the
  backend runner.
- When omitted, Melix records `validation_strategy = "none"` in the manifest and skips validation
  loss reporting rather than pretending validation exists.

### Derived-model alias behavior

- training may persist `desired_derived_model_alias` in the adapter package manifest
- activation accepts `derived_model_alias` explicitly and overrides the desired alias when both are
  present
- Window UI and CLI show the resolved alias that was actually activated

### Adapter-backed runtime behavior

- `fused_derived_model` remains the default activation mode
- `adapter_backed_runtime` becomes a supported alternative
- adapter-backed derived manifests point at the base model and adapter package instead of a fused
  export directory
- catalog entries for adapter-backed derived models remain text-capable model summaries and preserve
  `melix.adapter_set_hash`, `melix.activation_mode`, and `melix.derived_from_model_id`

### Derived-model removal behavior

- Melix adds `remove_derived_model` as an internal model operation on the existing maintenance path
- removal accepts a derived model ID or manifest path
- removal unloads the derived model if resident, deletes product-owned artifacts, refreshes the
  catalog snapshot, and records a lifecycle artifact
- repeated removal of a missing derived model fails with a typed negative path rather than silently
  succeeding

### Evaluation comparison behavior

- Melix adds a compare job family under the existing evaluation product surface
- comparison runs one base target plus one or more derived targets serially under one frozen suite
  definition and one frozen control set
- persisted outputs include suite deltas, paired sample rows, win/loss/tie counts, regression
  counts, and release-friendly summary exports
- CLI and Window UI expose comparison as an evaluation action, not as an operator-only manual
  recipe

## Data And Artifact Contracts

### Adapter package additions

The `melix.lora_adapter_package.v1` manifest grows the following stable fields:

- `training_mode`
- `quantization_mode`
- `validation_strategy`
- `validation_split`
- `validation_sample_count`
- `desired_derived_model_alias`
- `requested_acceptance_model_repo`

### Derived model manifest additions

The `melix.derived_text_model.v1` manifest grows the following stable fields:

- `activation_mode`
- `base_model_repo_id`
- `adapter_manifest_path`
- `adapter_weights_path`
- `derived_model_alias`
- `remove_supported`

### Evaluation comparison artifacts

Melix persists:

- `evaluation-compare-job.json`
- `evaluation-compare-summary.json`
- `evaluation-compare-summary.csv`
- `evaluation-compare-samples.jsonl`
- `evaluation-compare-report.md`

## Operator Surfaces

### CLI

The CLI remains the public automation-friendly surface and gains:

- `melix lora train --training-mode qlora`
- `melix lora train --hf-valid-split <split>`
- `melix lora activate --activation-mode adapter_backed_runtime`
- `melix lora remove-derived ...`
- `melix eval compare ...`

### Window UI

The Window UI must expose the same state transitions and clearly render:

- LoRA versus QLoRA training mode
- validation split selection
- fused versus adapter-backed activation mode
- derived-model remove action
- compare-to-base evaluation action and persisted comparison outputs

Execution mode is intentionally mixed:

- production UI calls the public `melix` subprocess path
- tests call the same shared CLI runner seam directly

This keeps the product path honest while making positive and negative UI tests deterministic.

## Metrics And Probes

This closure extends LoRA acceptance with the following required probes:

- `training.mode`
- `training.validation_strategy`
- `training.validation.loss_final`
- `training.validation.loss_best`
- `activation.mode`
- `activation.remove.duration_ms`
- `activation.remove.result`
- `eval.compare.delta`
- `eval.compare.win_count`
- `eval.compare.loss_count`
- `eval.compare.tie_count`
- `eval.compare.regression_count`

## Test And Acceptance Matrix

Each closure feature must prove both positive and negative behavior:

- unit tests in Python and Swift for request validation, manifests, catalog syncing, and failure
  typing
- CLI parser and runner tests for new flags, error paths, and output rendering
- Window UI tests for state wiring and visible lifecycle actions
- worker and control-plane end-to-end or smoke coverage for real job orchestration
- acceptance runbooks updated with concrete commands, output paths, screenshots, and job IDs using
  `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`

## Acceptance Exit Criteria

This closure is accepted only when all of the following are true:

- LoRA and QLoRA both train successfully against the fixed Qwen acceptance model
- Hugging Face training with `hf_valid_split` persists validation metadata and negative-path typing
- both fused and adapter-backed activation register loadable derived models
- `remove_derived_model` works from CLI and Window UI and rejects invalid requests cleanly
- `melix eval compare` persists paired base-versus-derived evidence and exports
- repository-owned CLI and Window UI acceptance tests pass
- the English runbooks describe the exact accepted workflow

## Delivery Workflow

Implementation is delivered in ordered phases rather than one long-lived unmerged branch:

1. complete one planned phase
2. run that phase's fresh verification
3. squash-merge the phase branch into local `main`
4. start the next phase from the updated local `main`

This workflow is part of acceptance because it keeps each phase independently verifiable and
prevents unreviewed cross-phase drift.

## Risks

- MLX-LM or MLX dependency differences may require subprocess-only QLoRA fallback on some machines
- adapter-backed serving may expose loader assumptions that previously only existed for fused
  derived models
- comparison jobs must preserve identical sample ordering across targets to keep deltas meaningful
- Window UI smoke coverage must stay deterministic even though the underlying jobs create real local
  artifacts
