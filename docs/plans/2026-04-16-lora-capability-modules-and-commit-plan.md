# Melix LoRA Capability Modules And Commit Plan

> **For Hermes:** Use the `subagent-driven-development` skill to execute one commit slice at a time. Do not collapse multiple commit slices into one implementation pass.

**Goal:** Decompose the next-stage Melix LoRA roadmap into product-level capability modules, then break each module into independently shippable commit slices with explicit file ownership, verification, and dependency order.

**Architecture:** Treat Melix LoRA as one end-to-end product path with seven top-level modules: adapter-backed runtime, adapter-native evaluation compare, training resilience and experiment management, training-mode expansion, artifact export and publish, target-module plus family expansion, and release-evidence orchestration. Each module below is intentionally split into commit-sized implementation slices so the repository can land value incrementally without waiting for one large all-or-nothing LoRA rewrite.

**Tech Stack:** Swift CLI and control plane, Python worker productization layer, MLX text runtime, MLX-LM LoRA stack, protocol schemas, repository-owned fixtures, pytest, Swift tests.

---

## Why this plan exists

Melix already ships:

- LoRA and QLoRA training
- adapter package artifacts
- fused derived-model activation
- evaluation compare against loaded target models
- adapter publish receipts and registry snapshots

The next product gap is not basic training. The real missing capabilities are:

1. a true non-fused adapter-backed runtime path
2. compare flows that can target adapters directly instead of only preloaded derived models
3. resume and experiment-grade training lifecycle controls
4. broader training modes such as DoRA, preference tuning, and continual pretraining
5. product-owned export and publish paths for adapter and merged artifacts
6. architecture-aware target expansion beyond the current text-first default path
7. release evidence that proves the full LoRA workflow, not only isolated slices

This plan is written to convert those needs into concrete modules and commit-ready execution slices.

The capability split and module ordering in this document are informed by code inspection of:

- `Goekdeniz-Guelmez/mlx-lm-lora`
- `ARahim3/mlx-tune`

Those repositories were used as comparison baselines for:

- richer LoRA training-mode breadth
- stronger adapter-only versus merged artifact handling
- clearer non-fused runtime semantics
- more productized adapter lifecycle and distribution flows

---

## Module 1: Real Adapter-Backed Runtime

**Product outcome:** `adapter_backed_runtime` becomes a real serving mode where Melix can run inference with `base model + adapter` directly, without forcing a fused local export first.

**Current state:** Activation metadata exists, but the strongest runtime closure today still belongs to `fused_derived_model`.

**Primary files:**
- `services/mlx-worker-python/worker/model_ops/adapter_activation_pipeline.py`
- `services/mlx-worker-python/worker/runtime/mlx_text_runtime.py`
- `services/mlx-worker-python/worker/engine/maintenance_core.py`
- `services/mlx-worker-python/worker/model_ops/job_registry.py`
- `services/mlx-worker-python/tests/test_lora_model_ops.py`
- `services/mlx-worker-python/tests/test_lora_model_ops_unit.py`
- `services/mlx-worker-python/tests/test_mlx_backend.py`

### Commit slice 1.1: Define adapter-backed runtime load contract

**Objective:** Make the worker runtime accept explicit adapter-backed load metadata instead of treating adapter-backed derived models as base-path aliases only.

**Files:**
- Modify: `services/mlx-worker-python/worker/runtime/mlx_text_runtime.py`
- Modify: `services/mlx-worker-python/worker/model_ops/adapter_activation_pipeline.py`
- Test: `services/mlx-worker-python/tests/test_lora_model_ops_unit.py`

**Steps:**
1. Add failing unit coverage that proves adapter-backed activation must pass adapter manifest and adapter weights metadata into the runtime load path.
2. Implement a runtime-load metadata shape that distinguishes:
   - fused derived model load
   - adapter-backed runtime load
3. Keep `melix.derived_text_model.v1` compatible while making adapter-backed fields explicit and non-optional for that mode.
4. Run:
   - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops_unit.py -q`
5. Commit:
   - `git commit -m "feat: define adapter-backed runtime load contract"`

### Commit slice 1.2: Wire adapter-backed load through the text runtime

**Objective:** Make the runtime actually load adapter-backed derived models with adapter-aware behavior.

**Files:**
- Modify: `services/mlx-worker-python/worker/runtime/mlx_text_runtime.py`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Test: `services/mlx-worker-python/tests/test_mlx_backend.py`
- Test: `services/mlx-worker-python/tests/test_lora_model_ops.py`

**Steps:**
1. Add failing tests that distinguish runtime behavior between base-only loads and adapter-backed loads.
2. Implement adapter-aware load semantics in the runtime backend path.
3. Preserve fused activation behavior and do not regress standard base-model load flows.
4. Run:
   - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_mlx_backend.py services/mlx-worker-python/tests/test_lora_model_ops.py -q`
5. Commit:
   - `git commit -m "feat: run adapter-backed derived models through runtime"`

### Commit slice 1.3: Surface runtime identity and health for adapter-backed models

**Objective:** Make registry snapshots and operator surfaces clearly show when a loaded model is adapter-backed and which adapter it uses.

**Files:**
- Modify: `services/mlx-worker-python/worker/model_ops/job_registry.py`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Test: `services/mlx-worker-python/tests/test_lora_model_ops.py`
- Test: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- Test: `Tests/MelixCLITests/MelixCLIRunnerTests.swift`

**Steps:**
1. Add failing snapshot and CLI tests for adapter-backed loaded model visibility.
2. Expose runtime identity fields for adapter-backed loads.
3. Make CLI output and JSON output distinguish fused vs adapter-backed derived models.
4. Run:
   - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops.py -q`
   - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests`
   - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter MelixCLIRunnerTests`
5. Commit:
   - `git commit -m "feat: surface adapter-backed runtime identity in snapshots"`

---

## Module 2: Adapter-Native Evaluation Compare

**Product outcome:** `eval compare` accepts adapter targets directly and can compare one base model against multiple adapters without requiring every target to be pre-materialized as a long-lived loaded model first.

**Primary files:**
- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/worker/productization/evaluation_compare.py`
- `services/mlx-worker-python/worker/productization/evaluation_store.py`
- `services/mlx-worker-python/tests/test_evaluation_core.py`
- `services/mlx-worker-python/tests/test_evaluation_store.py`
- `Tests/MelixCLITests/MelixCLIParserTests.swift`
- `Tests/MelixCLITests/MelixCLIRunnerTests.swift`

### Commit slice 2.1: Add adapter-target request contract for evaluation compare

**Objective:** Extend compare inputs so adapter manifests or adapter IDs can be used as first-class targets.

**Files:**
- Modify: `services/mlx-worker-python/worker/productization/evaluation_compare.py`
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Test: `services/mlx-worker-python/tests/test_evaluation_core.py`
- Test: `Tests/MelixCLITests/MelixCLIParserTests.swift`

**Steps:**
1. Add failing tests for `base model + multiple adapter targets`.
2. Define one canonical compare input shape for adapter-backed targets.
3. Keep existing `compare_target_model_ids` backward compatible.
4. Run:
   - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py -q`
   - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter MelixCLIParserTests`
5. Commit:
   - `git commit -m "feat: add adapter-native compare request contract"`

### Commit slice 2.2: Materialize adapter compare targets on demand

**Objective:** Let evaluation compare resolve adapter targets into temporary runtime-backed compare candidates automatically.

**Files:**
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `services/mlx-worker-python/worker/runtime/mlx_text_runtime.py`
- Test: `services/mlx-worker-python/tests/test_evaluation_core.py`

**Steps:**
1. Add failing compare tests that use adapters directly rather than preloaded target model IDs.
2. Implement temporary load and cleanup for compare-only adapter targets.
3. Preserve current loaded-model compare semantics.
4. Run:
   - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py -q`
5. Commit:
   - `git commit -m "feat: materialize adapter compare targets on demand"`

### Commit slice 2.3: Persist adapter compare lineage and reports

**Objective:** Make compare artifacts clearly record which adapter targets participated and how they were materialized.

**Files:**
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Test: `services/mlx-worker-python/tests/test_evaluation_store.py`
- Test: `Tests/MelixCLITests/MelixCLIRunnerTests.swift`

**Steps:**
1. Add failing persistence tests for adapter compare lineage fields.
2. Persist adapter target identity in compare JSON, CSV, and markdown reports.
3. Expose the lineage through CLI listing or export output.
4. Run:
   - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_store.py -q`
   - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter MelixCLIRunnerTests`
5. Commit:
   - `git commit -m "feat: persist adapter compare lineage in evaluation artifacts"`

---

## Module 3: Training Resilience And Experiment Management

**Product outcome:** LoRA training becomes resumable, checkpointed, inspectable, and comparable as a sequence of experiments rather than isolated one-shot jobs.

**Primary files:**
- `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`
- `services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py`
- `services/mlx-worker-python/worker/productization/lora_experiment_store.py`
- `services/mlx-worker-python/worker/model_ops/job_registry.py`
- `services/mlx-worker-python/tests/test_lora_experiment_store.py`
- `services/mlx-worker-python/tests/test_lora_model_ops.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`

### Commit slice 3.1: Add checkpoint and resume manifest fields

**Objective:** Extend training manifests so Melix can resume from prior adapter checkpoints safely.

**Files:**
- Modify: `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`
- Modify: `services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py`
- Test: `services/mlx-worker-python/tests/test_lora_model_ops.py`

**Steps:**
1. Add failing training tests for resume metadata.
2. Add canonical manifest fields for:
   - checkpoint count
   - latest checkpoint path
   - resume source path
   - resume-ready state
3. Run:
   - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops.py -q`
4. Commit:
   - `git commit -m "feat: add LoRA checkpoint and resume manifest metadata"`

### Commit slice 3.2: Productize local experiment index

**Objective:** Group related training runs into a reusable experiment index instead of only raw job history.

**Files:**
- Modify: `services/mlx-worker-python/worker/productization/lora_experiment_store.py`
- Modify: `services/mlx-worker-python/worker/model_ops/job_registry.py`
- Test: `services/mlx-worker-python/tests/test_lora_experiment_store.py`

**Steps:**
1. Add failing experiment-store tests for grouped runs and derived recommendations.
2. Persist experiment groups, presets, checkpoint lineage, and “best known adapter” metadata.
3. Run:
   - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_experiment_store.py -q`
4. Commit:
   - `git commit -m "feat: persist grouped LoRA experiments and checkpoints"`

### Commit slice 3.3: Surface resume and experiment status in operator flows

**Objective:** Make CLI and operator surfaces show whether a training run can be resumed and where it belongs in an experiment.

**Files:**
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Test: `Tests/MelixCLITests/MelixCLIRunnerTests.swift`
- Test: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`

**Steps:**
1. Add failing surface tests for experiment and resume metadata.
2. Expose grouped training runs and resume readiness through CLI and Window UI.
3. Run:
   - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIRunnerTests|RuntimeViewModelTests'`
4. Commit:
   - `git commit -m "feat: expose LoRA experiment and resume state in operator surfaces"`

---

## Module 4: Training-Mode Expansion

**Product outcome:** Melix grows from LoRA and QLoRA SFT into a broader local post-training platform.

**Primary files:**
- `services/mlx-worker-python/worker/model_ops/training_config.py`
- `services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py`
- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `services/mlx-worker-python/tests/test_training_dataset_builder.py`
- `services/mlx-worker-python/tests/test_lora_model_ops.py`
- `docs/runbooks/phase-8-lora-adapter-workflow.md`

### Commit slice 4.1: Add DoRA training mode contract

**Objective:** Introduce DoRA as a first-class training mode with explicit validation and manifest evidence.

**Files:**
- Modify: `services/mlx-worker-python/worker/model_ops/training_config.py`
- Modify: `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`
- Test: `services/mlx-worker-python/tests/test_lora_model_ops.py`

**Steps:**
1. Add failing tests for `training_mode=dora`.
2. Validate DoRA configuration and persist it into the adapter package manifest.
3. Run:
   - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops.py -q`
4. Commit:
   - `git commit -m "feat: add DoRA configuration to Melix LoRA training"`

### Commit slice 4.2: Add preference-tuning dataset and mode contracts

**Objective:** Prepare Melix for DPO-style or ORPO-style adapter training by adding explicit dataset and mode contracts.

**Files:**
- Modify: `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- Modify: `services/mlx-worker-python/worker/model_ops/training_config.py`
- Test: `services/mlx-worker-python/tests/test_training_dataset_builder.py`

**Steps:**
1. Add failing tests for preference-pair dataset materialization.
2. Add mode-specific dataset validation for preference workflows.
3. Keep standard SFT formats working unchanged.
4. Run:
   - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_training_dataset_builder.py -q`
5. Commit:
   - `git commit -m "feat: add preference-tuning dataset contracts for LoRA"`

### Commit slice 4.3: Add continual-pretraining mode boundary

**Objective:** Establish a product-owned CPT mode so Melix can support domain adaptation beyond response-only SFT.

**Files:**
- Modify: `services/mlx-worker-python/worker/model_ops/training_config.py`
- Modify: `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- Modify: `docs/runbooks/phase-8-lora-adapter-workflow.md`
- Test: `services/mlx-worker-python/tests/test_training_dataset_builder.py`

**Steps:**
1. Add failing tests for text-only CPT datasets.
2. Add configuration and validation for `training_mode=cpt` or equivalent productized mode naming.
3. Update the LoRA runbook to separate SFT and CPT expectations.
4. Run:
   - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_training_dataset_builder.py -q`
5. Commit:
   - `git commit -m "feat: add continual-pretraining mode contract for Melix training"`

---

## Module 5: Artifact Export, Publish, And Distribution

**Product outcome:** Melix treats adapter-only artifacts, merged artifacts, and published remote artifacts as first-class product outputs.

**Primary files:**
- `services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py`
- `services/mlx-worker-python/worker/model_ops/job_registry.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `Sources/MelixCLICore/MelixCLI.swift`
- `docs/runbooks/phase-8-lora-adapter-workflow.md`

### Commit slice 5.1: Split adapter export from merged export contract

**Objective:** Make adapter-only and merged-model export paths explicit rather than implying one generic publish path.

**Files:**
- Modify: `services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py`
- Modify: `services/mlx-worker-python/tests/test_maintenance_service.py`
- Modify: `docs/runbooks/phase-8-lora-adapter-workflow.md`

**Steps:**
1. Add failing tests that distinguish adapter export and merged-model export.
2. Define explicit artifact-kind handling and export metadata.
3. Update the runbook so operators know when to export adapter-only versus merged outputs.
4. Run:
   - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_maintenance_service.py -q`
5. Commit:
   - `git commit -m "feat: split adapter and merged export contracts"`

### Commit slice 5.2: Record real publish lineage in the registry

**Objective:** Make the registry snapshot show where an adapter or merged artifact was published and from which local lineage it came.

**Files:**
- Modify: `services/mlx-worker-python/worker/model_ops/job_registry.py`
- Modify: `services/mlx-worker-python/tests/test_maintenance_service.py`

**Steps:**
1. Add failing registry tests for publish lineage fields.
2. Persist `published_repo`, publish backend, artifact kind, and parent lineage.
3. Run:
   - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_maintenance_service.py -q`
4. Commit:
   - `git commit -m "feat: record publish lineage for LoRA artifacts"`

### Commit slice 5.3: Add CLI surfaces for export and publish selection

**Objective:** Give operators clear CLI entry points for adapter export, merged export, and publish status.

**Files:**
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Test: `Tests/MelixCLITests/MelixCLIParserTests.swift`
- Test: `Tests/MelixCLITests/MelixCLIRunnerTests.swift`

**Steps:**
1. Add failing parser and runner tests for export and publish mode selection.
2. Implement clear subcommands or flags for export and publish workflows.
3. Run:
   - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests'`
4. Commit:
   - `git commit -m "feat: add explicit CLI surfaces for LoRA export and publish"`

---

## Module 6: Target-Module And Family Expansion

**Product outcome:** Melix picks smarter default LoRA targets and supports a broader set of model families cleanly.

**Primary files:**
- `services/mlx-worker-python/worker/model_ops/training_config.py`
- `services/mlx-worker-python/worker/model_registry/catalog.py`
- `services/mlx-worker-python/tests/test_lora_model_ops.py`
- `services/mlx-worker-python/tests/test_training_dataset_builder.py`
- `docs/runbooks/phase-8-lora-adapter-workflow.md`

### Commit slice 6.1: Add architecture-aware target-module presets

**Objective:** Resolve target modules by family profile instead of relying mainly on generic text defaults.

**Files:**
- Modify: `services/mlx-worker-python/worker/model_ops/training_config.py`
- Test: `services/mlx-worker-python/tests/test_lora_model_ops.py`

**Steps:**
1. Add failing tests for Qwen, Gemma, and Kimi family target resolution.
2. Implement explicit per-family target-module presets.
3. Run:
   - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops.py -q`
4. Commit:
   - `git commit -m "feat: add architecture-aware LoRA target presets"`

### Commit slice 6.2: Add advanced-family expansion hooks

**Objective:** Prepare Melix for MoE-style or embedding-style LoRA support without mixing those rules into the dense text baseline.

**Files:**
- Modify: `services/mlx-worker-python/worker/model_registry/catalog.py`
- Modify: `services/mlx-worker-python/worker/model_ops/training_config.py`
- Test: `services/mlx-worker-python/tests/test_lora_model_ops.py`

**Steps:**
1. Add failing tests for advanced family detection hooks.
2. Separate dense, MoE, and embedding family capability paths cleanly.
3. Run:
   - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops.py -q`
4. Commit:
   - `git commit -m "feat: separate dense and advanced-family LoRA capability hooks"`

### Commit slice 6.3: Document family-level support expectations

**Objective:** Make operators understand which families are stable, experimental, or blocked for LoRA workflows.

**Files:**
- Modify: `docs/runbooks/phase-8-lora-adapter-workflow.md`
- Modify: `docs/current-status.md`

**Steps:**
1. Document stable family support, experimental family support, and explicit unsupported paths.
2. Keep the docs honest about which routes are production-ready.
3. Commit:
   - `git commit -m "docs: clarify LoRA family support boundaries"`

---

## Module 7: Release Evidence And Workflow Orchestration

**Product outcome:** Melix can prove that `dataset -> train -> activate -> compare -> publish` works as one product path and can report that path in release evidence.

**Primary files:**
- `services/mlx-worker-python/worker/productization/release_gates.py`
- `services/mlx-worker-python/worker/productization/acceptance_metrics.py`
- `scripts/phase8_acceptance_bundle.py`
- `services/mlx-worker-python/tests/test_release_gates.py`
- `tests/test_phase8_acceptance_bundle.py`
- `docs/runbooks/phase-8-release-gates.md`

### Commit slice 7.1: Add full LoRA path evidence metrics

**Objective:** Record metrics for each stage in the LoRA product path instead of only isolated job success.

**Files:**
- Modify: `services/mlx-worker-python/worker/productization/acceptance_metrics.py`
- Modify: `services/mlx-worker-python/worker/productization/release_gates.py`
- Test: `services/mlx-worker-python/tests/test_release_gates.py`

**Steps:**
1. Add failing tests for per-stage LoRA workflow metrics.
2. Record success and failure counters for:
   - dataset build
   - train
   - activate
   - compare
   - publish
3. Run:
   - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_release_gates.py -q`
4. Commit:
   - `git commit -m "feat: add full-path LoRA release evidence metrics"`

### Commit slice 7.2: Extend acceptance bundle capture for LoRA capability evidence

**Objective:** Persist enough artifact evidence to audit a whole LoRA capability run after the fact.

**Files:**
- Modify: `scripts/phase8_acceptance_bundle.py`
- Modify: `tests/test_phase8_acceptance_bundle.py`

**Steps:**
1. Add failing tests for LoRA-path evidence bundle fields.
2. Capture:
   - adapter artifact
   - activation artifact
   - compare artifact
   - publish artifact
   - runtime mode used
3. Run:
   - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest tests/test_phase8_acceptance_bundle.py -q`
4. Commit:
   - `git commit -m "feat: extend acceptance bundle with LoRA capability evidence"`

### Commit slice 7.3: Document the release contract for LoRA capability closure

**Objective:** Make the release-gate rule explicit in docs so operators know what counts as LoRA workflow closure.

**Files:**
- Modify: `docs/runbooks/phase-8-release-gates.md`
- Modify: `docs/current-status.md`

**Steps:**
1. Document the release requirement for end-to-end LoRA evidence.
2. Distinguish deterministic smoke evidence from live runtime evidence.
3. Commit:
   - `git commit -m "docs: define release evidence contract for LoRA capability closure"`

---

## Recommended Execution Order

Do not execute modules in arbitrary order. The intended order is:

1. Module 1 — Real Adapter-Backed Runtime
2. Module 2 — Adapter-Native Evaluation Compare
3. Module 3 — Training Resilience And Experiment Management
4. Module 5 — Artifact Export, Publish, And Distribution
5. Module 7 — Release Evidence And Workflow Orchestration
6. Module 6 — Target-Module And Family Expansion
7. Module 4 — Training-Mode Expansion

Reasoning:
- runtime truth must exist before compare can rely on adapters directly
- compare and experiment workflows are easier to validate once runtime truth exists
- publish and release evidence should follow the real runtime path, not precede it
- broader training modes should land after the base lifecycle is operationally solid

---

## Global Verification Commands

Use these commands repeatedly after each relevant commit slice.

### Python worker scope

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python pytest \
  services/mlx-worker-python/tests/test_lora_model_ops.py \
  services/mlx-worker-python/tests/test_lora_model_ops_unit.py \
  services/mlx-worker-python/tests/test_evaluation_core.py \
  services/mlx-worker-python/tests/test_evaluation_store.py \
  services/mlx-worker-python/tests/test_lora_experiment_store.py \
  services/mlx-worker-python/tests/test_maintenance_service.py \
  services/mlx-worker-python/tests/test_release_gates.py -q
```

### Swift control-plane scope

```bash
HOME="$(pwd)/.swift-home" \
CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" \
swift test --package-path services/control-plane-swift \
  --filter 'PythonBridgeWorkerClientTests|ControlPlaneServiceTests'
```

### Public CLI scope

```bash
HOME="$(pwd)/.swift-home" \
CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" \
swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests'
```

### Acceptance bundle scope

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python pytest \
  tests/test_phase8_acceptance_bundle.py -q
```

---

## Expected PR Strategy

This document should not be implemented in one PR. The right PR strategy is:

- one PR to land this decomposition document
- then one PR per module or tightly related pair of commit slices
- keep each PR narrow enough that the review story is obvious
- prefer merge order that preserves runtime truth before product-surface polish

The repository should treat this document as the planning source of truth for post-Phase-8 LoRA expansion until a newer LoRA capability plan explicitly supersedes it.
