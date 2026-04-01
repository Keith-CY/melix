# Real LoRA Closed-Loop Implementation

## Goal

Implement a real Melix LoRA training and activation loop without adding new public RPC surfaces. Keep `RunModelOperation` and `ConvertModelRequest` as the orchestration substrate, replace placeholder training behavior with MLX-backed execution, and hand activated adapters back to the existing text-serving path as adapter-scoped derived models.

## Scope

- replace the placeholder `train_lora` maintenance path with a real dataset-validated, MLX-backed training pipeline
- add stable local dataset and adapter package formats for reproducible training and publishing
- add LoRA config mapping, family-aware module expansion, strategy switches, and typed failure handling
- add `activate_adapter` as a local serving handoff that produces `melix.derived_text_model.v1`
- register activated derived models in the control-plane catalog and preserve adapter-aware cache identity
- extend native desktop tooling so adapter rows show training, activation, export, and publish state
- document the implementation plan, design inputs, and the operator runbook for dataset preparation, training, activation, verification, publishing, and cleanup

## Non-Goals

- add new public proto RPCs or new serving endpoints
- implement QLoRA in v1
- expose adapter-backed runtime activation as the default desktop path in v1
- add remote dataset fetch or cloud training orchestration
- publish fused derived serving directories instead of adapter packages

## Files

- add `services/mlx-worker-python/worker/model_ops/errors.py`
- add `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- add `services/mlx-worker-python/worker/model_ops/training_config.py`
- add `services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py`
- add `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`
- add `services/mlx-worker-python/worker/model_ops/adapter_activation_pipeline.py`
- update `services/mlx-worker-python/worker/engine/maintenance_core.py`
- update `services/mlx-worker-python/worker/model_ops/job_registry.py`
- add `services/mlx-worker-python/tests/test_lora_model_ops.py`
- update `services/mlx-worker-python/tests/test_maintenance_service.py`
- update `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- update `services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift`
- update `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- update `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`
- update `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- update `services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift`
- update `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- update `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`
- update `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- update `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- add `docs/runbooks/phase-8-lora-adapter-workflow.md`

## Design Inputs From `mlx-tune`

Melix does not simply call `mlx_lm.tuner` directly and stop there. The `mlx-tune` design pattern is useful because it wraps backend primitives with product-facing normalization, orchestration, and artifact contracts that are needed for repeatable local workflows.

### Why Melix Does More Than A Thin `mlx_lm.tuner` Call

- `mlx_lm` exposes backend execution primitives, but Melix needs operator-facing settings such as compact target-module names, family defaults, local dataset package inputs, and manifest-oriented outputs.
- Melix must preserve compatibility with the existing control-plane and model-ops substrate instead of introducing a backend-native training API.
- Melix must persist stable adapter identity, publishing metadata, activation metadata, and catalog-ready derived-model metadata so the result can re-enter serving and desktop tooling cleanly.

### Adopted `mlx-tune`-Style Inputs

- LoRA config mapping and module expansion:
  Melix accepts compact LoRA settings and expands them into backend-specific module paths based on text-family metadata.
- Training orchestration:
  Melix owns the end-to-end stage model, progress emission, metrics recording, checkpoint cadence, and native-versus-subprocess fallback behavior.
- Dataset normalization:
  Melix validates local dataset packages, converts supported input styles into one backend-ready normalized shape, and stores a reproducible normalized snapshot inside the job output.
- Strategy switches:
  Melix exposes response-only masking, prompt masking, gradient checkpointing, and max-sequence controls as operator-visible flags instead of ad hoc backend-only arguments.
- Richer adapter artifacts:
  Melix persists adapter config, normalized-dataset metadata, stable hashes, export-ready metadata, and publish metadata instead of only emitting raw LoRA weights.
- Serving handoff:
  Melix adds a local activation step that turns a trained adapter into a fused derived text model or a future adapter-backed target without changing public RPCs.

## Internal Contracts

### Stable Internal Operations

- `train_lora`
- `activate_adapter`
- `upload`
- `registry_snapshot`

### Stable Local Package Formats

- `melix.training_dataset_package.v1`
- `melix.lora_adapter_package.v1`
- `melix.derived_text_model.v1`

### Public Interface Constraint

- keep `packages/protocol/schema/controlplane/v1/control_plane.proto` unchanged
- keep `packages/protocol/schema/worker/v1/maintenance.proto` unchanged

## Implementation Checklist

### 1. Real LoRA Execution Path

- [ ] validate `manifest.json` and `samples.jsonl` before training starts
- [ ] resolve the base text family and reject unsupported families with typed errors
- [ ] normalize operator-visible LoRA settings into backend-ready config
- [ ] stage normalized dataset files under the job output for reproducibility
- [ ] run native MLX-LM training when available
- [ ] fall back to subprocess execution for supported native-unavailable cases
- [ ] persist real metrics and emit structured progress stages

### 2. LoRA Config Mapping And Module Expansion

- [ ] support compact target modules such as `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, and `down_proj`
- [ ] expand modules into family-specific paths before backend invocation
- [ ] source default target modules from family metadata rather than one global list
- [ ] keep a typed unsupported path for `training_mode=qlora`

### 3. Training Orchestration

- [ ] emit the stage sequence `resolve_source`, `validate_dataset`, `normalize_config`, `prepare_training_data`, `apply_lora`, `train`, `write_adapter`, `write_manifest`
- [ ] record `training.job_duration_ms`, `training.tokens_seen`, `training.examples_seen`, `training.loss_final`, `training.loss_best`, and `training.learning_rate_final`
- [ ] persist typed errors for invalid dataset packages, unsupported families, unsupported target modules, missing MLX runtime, backend failures, and activation failures

### 4. Data-Layer Adaptation

- [ ] require `schema_version`, `dataset_id`, `format`, `sample_count`, and `version` in dataset manifests
- [ ] support `chat_messages`, `prompt_completion`, and `text_completion`
- [ ] validate chat ordering and supervised-target shape
- [ ] support deterministic sample limiting and truncation for development smoke jobs
- [ ] persist a canonical normalized snapshot under the output directory

### 5. Training Strategy Switches

- [ ] expose `response_only`, `gradient_checkpointing`, `mask_prompt`, and `max_seq_length`
- [ ] default `response_only=true` for chat-style datasets
- [ ] default `gradient_checkpointing=false` unless explicitly enabled or required later by family policy
- [ ] fail early when response-only supervision is requested for unsupported dataset shapes

### 6. Adapter Artifact Management

- [ ] emit `melix.lora_adapter_package.v1` instead of placeholder adapter JSON
- [ ] persist backend-native weights, backend-required adapter config, normalized-dataset manifest path, target-module expansion, and stable adapter identity
- [ ] surface train status, activate status, exportability state, and publish state through registry snapshots
- [ ] keep enough metadata for later load, fuse, export, and publish workflows

### 7. Serving Handoff

- [ ] add `activate_adapter` with `fused_derived_model` and reserved `adapter_backed_runtime` activation modes
- [ ] keep `fused_derived_model` as the v1 default
- [ ] return `derived_model_id`, `derived_model_path`, `activation_duration_ms`, and `adapter_set_hash`
- [ ] register activated derived models as ordinary text models in the control-plane catalog
- [ ] preserve `melix.adapter_set_hash` across serving and cache identity

### 8. Control-Plane And Desktop Integration

- [ ] forward `activate_adapter` through the control plane
- [ ] record real training and activation metrics
- [ ] insert activated derived models into the text-capable catalog
- [ ] show trained, activated, published, failed, and pending-activation adapter states in the native shell
- [ ] show response-only and gradient-checkpointing flags in adapter details

## Verification

- `PYTHONPATH="/Users/ChenYu/Documents/Github/melix/.worktrees/codex-real-lora-closed-loop:/Users/ChenYu/Documents/Github/melix/.worktrees/codex-real-lora-closed-loop/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_lora_model_ops.py -q`
- `swift test --package-path services/control-plane-swift --filter PythonBridgeWorkerClientTests`
- `swift test --package-path services/control-plane-swift --filter ModelCatalogTests`
- `swift test --package-path services/control-plane-swift --filter executeRegistersActivatedDerivedModelsIntoTheCatalog`
- `swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests`
- `swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests`
- `make py-test`
- `make swift-test`
- `make integration-test`

## Acceptance

- `train_lora` produces a real adapter manifest and adapter files instead of placeholder metrics
- invalid dataset packages and unsupported module selections fail with typed errors
- family-aware target-module expansion is stored in the adapter package
- response-only and gradient-checkpointing settings flow from operator inputs into runner config and persisted manifests
- `activate_adapter` produces a derived model manifest and registers a text-capable derived model into the control-plane catalog
- native desktop tooling shows real adapter lifecycle state from backend snapshots rather than placeholder labels
- adapter-aware cache identity uses real adapter hashes instead of placeholder metadata

## Assumptions And Known Constraints

- v1 implements LoRA only; QLoRA remains explicitly deferred
- v1 activation defaults to fused local derived models even though the internal operation contract reserves adapter-backed runtime mode
- v1 dataset ingestion is local-package only
- adapter publishing uploads the adapter package and not the fused derived serving directory
- the broader Swift workspace may still contain unrelated compile or test blockers outside this touched slice, so package-scoped targeted verification is the primary evidence for this implementation
