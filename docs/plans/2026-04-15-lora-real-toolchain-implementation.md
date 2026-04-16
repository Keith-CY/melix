# LoRA Real Toolchain Implementation Plan

## Goal

Implement the approved LoRA hardening plan so Melix closes the real operator path for:

- dataset preparation
- LoRA and QLoRA training
- derived-model activation and runtime loading
- evaluation compare
- publish
- release evidence

This plan extends the 2026-04-09 LoRA closure work from product-shape completeness to real
runtime, real publish, and real experiment evidence.

## Fixed Product Decisions

- `adapter_backed_runtime` must be a real serving mode, not metadata-only activation.
- adapter publish uses Hugging Face Hub as the only real publish backend in this slice.
- experiment persistence stays local-first with files plus a structured local index, not a DB.
- CLI and Window UI remain parity surfaces for the LoRA workflow.
- release evidence remains dual-layer:
  - deterministic baseline gate
  - real workload gate
- real evidence must cover Qwen, Gemma, and Kimi family paths.

## Current Baseline On 2026-04-15

- Targeted worker LoRA baseline:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py -q`
  - Result: `39 passed`
- Targeted Swift CLI baseline:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests'`
  - Result: build completed, then an existing `MelixCLIRunnerTests` failure remained in the
    `eval export commands write summary csv and sample artifacts with code evidence` path.
  - This failure is treated as pre-existing until proven otherwise.

## Implementation Strategy

Deliver the work in verified vertical slices. Each slice must start with failing tests and end with
fresh targeted verification.

### Slice 1: Real adapter-backed runtime

Close the current gap where `adapter_backed_runtime` only writes manifests but still loads the base
path without adapter semantics.

Implementation targets:

- worker runtime loading path
- adapter activation manifest shape
- control-plane load request metadata propagation
- runtime tests that prove adapter-aware load behavior

Success criteria:

- derived models activated as `adapter_backed_runtime` load through the worker with the adapter
  manifest and weights metadata present
- the runtime backend receives adapter-aware load inputs
- activation and serving metadata remain visible in catalog and job registry snapshots

Required probes:

- `activation.mode`
- `activation.adapter_backed.load_ms`
- `activation.adapter_backed.result`

### Slice 2: Real publish to Hugging Face Hub

Replace the local receipt-only path with a real adapter publish path.

Implementation targets:

- worker publish pipeline
- local publish artifact contract
- job registry publish state
- CLI and Window UI publish action and status text

Success criteria:

- publish persists a real remote repository reference
- publish status distinguishes success, skipped, and failure
- local receipts remain evidence artifacts, but not the backend itself

Required probes:

- `training.adapter_publish_ms`
- `training.adapter_publish_backend`
- `training.adapter_publish_result`

### Slice 3: Family closure for Qwen, Gemma, and Kimi

Expand LoRA training family selection beyond the current llama-like fallback.

Implementation targets:

- family detection heuristics
- family-specific training defaults and validation
- family tests for Qwen, Gemma, and Kimi identifiers and paths

Success criteria:

- each family resolves to a stable explicit profile
- unsupported combinations fail explicitly

### Slice 4: Dataset builder and inspection

Productize dataset preparation rather than only accepting already-packaged inputs.

Implementation targets:

- dataset builder manifests
- sample preview output
- automatic train or validation split
- token length statistics
- dirty sample and duplicate detection
- common dataset template conversion

Success criteria:

- operator surfaces can build or inspect a dataset package before training
- the dataset package records preview, stats, validation split policy, and quality findings

Required probes:

- `dataset.sample_count`
- `dataset.duplicate_count`
- `dataset.dirty_count`
- `dataset.prompt_tokens_p95`

### Slice 5: Experiment management

Promote LoRA runs from history rows to a reusable experiment system.

Implementation targets:

- runs grouping and local index
- parameter presets
- resume and checkpoint metadata
- loss and validation curves
- throughput and peak memory logging
- sweep manifests
- best-checkpoint recommendation

Success criteria:

- training outputs can be resumed and compared without manual file spelunking
- UI and CLI can read the same experiment state

Required probes:

- `experiment.resume_ready`
- `experiment.checkpoint_count`
- `training.tokens_per_second`
- `training.peak_memory_gb`

### Slice 6: Productized compare and release evidence

Close the workflow from activated derived model to compare to publish to release evidence.

Implementation targets:

- compare support for custom dataset sources
- compare outputs that survive reload and UI presentation
- release gate expansion from deterministic-only evidence to dual-layer evidence
- real workload evidence for Qwen, Gemma, and Kimi

Success criteria:

- `Dataset -> Train -> Activate/Test -> Compare -> Publish` works as one product path
- release evidence clearly separates deterministic and live workload outcomes

Required probes:

- `eval.compare.delta`
- `eval.compare.regression_count`
- `release_gate.real_workload.pass_count`
- `release_gate.real_workload.failure_count`

## File Groups

### Worker

- `services/mlx-worker-python/worker/model_ops/adapter_activation_pipeline.py`
- `services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py`
- `services/mlx-worker-python/worker/model_ops/training_config.py`
- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `services/mlx-worker-python/worker/model_ops/job_registry.py`
- `services/mlx-worker-python/worker/runtime/mlx_text_runtime.py`
- `services/mlx-worker-python/worker/engine/maintenance_core.py`
- `services/mlx-worker-python/worker/productization/evaluation_compare.py`
- `services/mlx-worker-python/worker/productization/release_gates.py`

### Swift surfaces

- `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- `Sources/MelixCLICore/MelixCLI.swift`
- `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`

### Tests

- `services/mlx-worker-python/tests/test_lora_model_ops.py`
- `services/mlx-worker-python/tests/test_lora_model_ops_unit.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`
- `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- `Tests/MelixCLITests/MelixCLIParserTests.swift`
- `Tests/MelixCLITests/MelixCLIRunnerTests.swift`
- `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`

## Verification Workflow

For each slice:

1. add or tighten a failing targeted test
2. run the targeted command and confirm the expected failure
3. implement the minimum code to pass
4. rerun the targeted command
5. update metrics and artifact evidence if the slice changes observability

Planned verification commands:

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py services/mlx-worker-python/tests/test_maintenance_service.py -q`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'PythonBridgeWorkerClientTests|ControlPlaneServiceTests'`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests'`

## Metrics Report Policy

Each completed slice must end with a changed-scope metrics report. If a slice is documentation-only
or the probe is not yet measurable, record `N/A` with the explicit reason.

## Current Execution Slice On 2026-04-15

This execution round continues Slice 4 with one explicit vertical cut:

- add a real dataset builder and inspector behind `melix lora dataset inspect` and
  `melix lora dataset build`
- support local JSONL sources plus Hugging Face dataset sources
- support common template conversion for `alpaca` and `sharegpt`, plus pass-through for
  `chat_messages`, `prompt_completion`, and `text_completion`
- emit preview samples, deterministic auto validation split metadata, duplicate and dirty sample
  findings, and approximate token length statistics in the built dataset manifest
- keep the dataset package compatible with the existing LoRA training loader so the output can feed
  directly into `melix lora train`

Slice-specific probes for this round:

- `dataset.sample_count`
- `dataset.validation_sample_count`
- `dataset.duplicate_count`
- `dataset.dirty_count`
- `dataset.prompt_tokens_p95`

### Verification Results

- Python changed-scope verification:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_mlx_backend.py -q`
  - Result: `146 passed`
- Swift changed-scope verification:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests/parsesLoraDatasetInspectCommand'`
  - Result: `1 test passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests/parsesLoraDatasetBuildCommandForHFDataset'`
  - Result: `1 test passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIRunnerTests/loraDatasetInspectForwardsExpectedOperationPayload'`
  - Result: `1 test passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIRunnerTests/loraDatasetBuildForwardsExpectedOperationPayload'`
  - Result: `1 test passed`

### Metrics Report

- `dataset.sample_count`: measured in builder manifests and asserted in Python tests
- `dataset.validation_sample_count`: measured in builder manifests and asserted in Python tests
- `dataset.duplicate_count`: measured in `quality.duplicate_count` and asserted in Python tests
- `dataset.dirty_count`: measured in `quality.dirty_count` and asserted in Python tests
- `dataset.prompt_tokens_p95`: measured in `token_stats.prompt_tokens_p95` with `whitespace_v1`
  estimator and asserted in Python tests

## Follow-on Execution Slice On 2026-04-15

This execution round advances Slice 6 with one explicit workflow cut:

- allow Evaluation Compare to run against custom dataset sources from the Window UI
- verify the direct control-plane request path carries `local_jsonl` source configuration together
  with compare parameters
- keep the worker-side compare path grounded on real materialized dataset packages instead of
  builtin-only assumptions
- restore menu bar package buildability after the new `melix lora dataset inspect` and
  `melix lora dataset build` CLI commands extended the shared command enum

Slice-specific probes for this round:

- `eval.compare.delta`
- `eval.compare.regression_count`

### Verification Results

- Swift changed-scope verification:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests/evaluationCompareSupportsCustomJSONLDatasetSources'`
  - Result: `1 test passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests/evaluationConfigurationForwardsStructuredSourceMappingAndProfileControls'`
  - Result: `1 test passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests/loraRemoveAndCompareGuardRailsRequireConcreteTargets'`
  - Result: `1 test passed`
- Python changed-scope verification:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_maintenance_service.py::test_run_evaluation_materializes_local_jsonl_source_for_compare_from_request services/mlx-worker-python/tests/test_evaluation_core.py::test_worker_maintenance_service_run_evaluation_maps_compare_results -q`
  - Result: `2 passed`

### Metrics Report

- `eval.compare.delta`: `N/A` in this slice because the changed scope only verifies request
  dispatch and dataset materialization, not persisted compare report values
- `eval.compare.regression_count`: `N/A` in this slice because no new end-to-end compare artifact
  bundle was produced during the targeted Window UI and worker plumbing verification

## CLI Parity Slice On 2026-04-15

This execution round advances Slice 6 on the CLI surface:

- add custom evaluation dataset source support to `melix eval run`
- add custom evaluation dataset source support to `melix eval compare`
- carry field mapping and evaluation profile controls through parser and runner layers
- preserve builtin-package behavior by only auto-defaulting `dataset_id` when no custom source is
  selected
- extend subprocess compare argument serialization so custom source and profile flags survive the
  subprocess bridge

Slice-specific probes for this round:

- `eval.compare.delta`
- `eval.compare.regression_count`

### Verification Results

- Swift changed-scope verification:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests/parsesEvalRunWithCustomHFDatasetSource'`
  - Result: `1 test passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests/parsesEvalCompareWithCustomJSONLSource'`
  - Result: `1 test passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIRunnerTests/evalRunForwardsCustomHFDatasetSourceMappingAndProfileControls'`
  - Result: `1 test passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIRunnerTests/evalCompareForwardsCustomJSONLSourceMappingAndProfileControls'`
  - Result: `1 test passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIRunnerTests/subprocessBackedEvaluationCompareSupportsRepoTargetsAndNestedResults'`
  - Result: `1 test passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIRunnerTests/evalComparePreloadsBaseAndTargetsAndReturnsJSON'`
  - Result: `1 test passed`

### Metrics Report

- `eval.compare.delta`: `N/A` in this slice because the changed scope only verifies CLI request
  construction and dispatch, not persisted compare score deltas
- `eval.compare.regression_count`: `N/A` in this slice because no release-gate or compare artifact
  bundle was produced during parser and runner verification

## Release Evidence Slice On 2026-04-16

This execution round advances Slice 6 on release evidence:

- add a distinct `real_workload` release-gate layer beside the deterministic baseline evidence
- require family-scoped real workload coverage for `qwen`, `gemma`, and `kimi`
- make the release gate fail closed when real workload evidence is missing or incomplete
- surface real workload release-gate counts through the phase-8 acceptance metrics report
- normalize deterministic evaluation evidence so the release gate receives the expected
  `eval.<suite>.accuracy` metric alias

Slice-specific probes for this round:

- `release_gate.real_workload.pass_count`
- `release_gate.real_workload.failure_count`

### Verification Results

- Python changed-scope verification:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_release_gates.py services/mlx-worker-python/tests/test_acceptance_metrics.py -q`
  - Result: `57 passed`

### Metrics Report

- `release_gate.real_workload.pass_count`: measured from family-scoped real workload evidence and
  surfaced in phase-8 acceptance metrics
- `release_gate.real_workload.failure_count`: measured from family-scoped real workload evidence
  and surfaced in phase-8 acceptance metrics
- `release_gate.real_workload.family_count`: measured in the release-gate summary as supporting
  evidence for required family coverage

## Experiment Metadata Slice On 2026-04-16

This execution round advances Slice 5 with one probe-bearing vertical cut:

- extend LoRA training results so adapter manifests persist checkpoint and resume readiness metadata
- persist training throughput and peak memory probes in the adapter package manifest
- surface the same experiment fields through the local registry adapter rows
- decode the new experiment fields in the Window UI model-tooling state
- render checkpoint or resume and throughput or memory summaries directly in the tools workspace

Slice-specific probes for this round:

- `experiment.resume_ready`
- `experiment.checkpoint_count`
- `training.tokens_per_second`
- `training.peak_memory_gb`

### Verification Results

- Python changed-scope verification:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_maintenance_service.py -q`
  - Result: `110 passed`
- Swift changed-scope verification:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests`
  - Result: `182 tests passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests`
  - Result: `95 tests passed`

### Metrics Report

- `experiment.resume_ready`: measured from the training result and persisted into the adapter
  manifest plus registry and Window UI state
- `experiment.checkpoint_count`: measured from the training result and persisted into the adapter
  manifest plus registry and Window UI state
- `training.tokens_per_second`: measured from the training result and persisted into the adapter
  manifest plus registry and Window UI state
- `training.peak_memory_gb`: measured from the training result and persisted into the adapter
  manifest plus registry and Window UI state

## Experiment Index Slice On 2026-04-16

This execution round advances Slice 5 from per-run metadata to reusable experiment management:

- add named LoRA training presets in the worker normalization path
- persist `preset_id`, `preset_title`, `experiment_group_id`, and `experiment_group_title` into
  training adapter manifests
- build and maintain a local-first experiment index at
  `model-ops/train_lora/lora-experiments.index.json`
- aggregate grouped run summaries with recommended manifest pointers for CLI and Window UI reuse
- add CLI support for `--preset` and `--experiment-group` on `melix lora train`
- render grouped experiment summaries in `melix lora list`
- decode grouped experiment summaries in the Window UI and expose preset plus experiment-group
  controls in the LoRA training workflow

Slice-specific probes for this round:

- `experiment.resume_ready`
- `experiment.checkpoint_count`
- `training.tokens_per_second`
- `training.peak_memory_gb`

### Verification Results

- Red verification before implementation:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_runtime_edges.py -k deterministic_lora_runner_train_native_writes_adapter_artifacts -q`
  - Result: `1 failed` because direct `LoRATrainingConfig(...)` construction did not provide
    `preset_id` and `preset_title`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests/lora'`
  - Result: parser failed to capture `preset_id` and `experiment_group_id`; runner output did not
    render `experiment_groups`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests`
  - Result: compile failures because `RuntimeViewModel` did not yet define
    `selectedLoraTrainingPreset`, `loraExperimentGroupID`, or `loraExperimentGroups`
- Green verification after implementation:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops_unit.py services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_runtime_edges.py -q`
  - Result: `164 passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests/lora'`
  - Result: `48 tests passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests`
  - Result: `182 tests passed`

### Metrics Report

- `experiment.resume_ready`: measured in the worker training result, persisted into adapter
  manifests and the local experiment index, and rendered in grouped Window UI summaries
- `experiment.checkpoint_count`: measured in the worker training result, persisted into adapter
  manifests and the local experiment index, and rendered in grouped Window UI summaries
- `training.tokens_per_second`: measured in the worker training result, persisted into adapter
  manifests and the local experiment index, and rendered in grouped CLI and Window UI summaries
- `training.peak_memory_gb`: measured in the worker training result, persisted into adapter
  manifests and the local experiment index, and rendered in grouped CLI and Window UI summaries

## Real Small-Model CLI E2E Slice On 2026-04-16

This execution round advances Slice 6 with the first true small-model LoRA acceptance cut on the
CLI primary path:

- add `--max-steps` to `melix lora train` and clamp worker-computed iterations with an explicit
  public step cap
- extend the phase-8 CLI acceptance bundle with a `real_small_model` execution profile
- make the real profile use `debug_fast`, `phase8-real-small-model`, and
  `adapter_backed_runtime` by default
- fix the real profile on `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`
- resolve real-model source in this order:
  - explicit CLI source flags
  - `MELIX_PHASE8_REAL_SMALL_MODEL_PATH` when it points to a local directory
  - Melix-managed Hub download fallback when the env path is unset or invalid
- persist experiment-index evidence and grouped registry evidence into the acceptance bundle
- keep real publish implemented in product code, but make the `real_small_model` acceptance profile
  explicit `skip publish` evidence:
  - do not attempt `melix upload` in the acceptance profile
  - record `publish.mode=disabled`, `publish.status=disabled`, and
    `publish.skip_reason=publish_disabled`
- add an explicit opt-in real E2E entrypoint:
  - `make phase8-real-e2e`
  - sets `MELIX_PHASE8_REAL_SMALL_MODEL_E2E=1`
  - runs the targeted real-stack integration test without changing default `integration-test`

Slice-specific probes for this round:

- `training.max_steps`
- `runtime.activation_mode`
- `experiment.index_exists`
- `publish.status`

### Verification Results

- Red verification before implementation:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter MelixCLIParserTests`
  - Result: `MelixCLIParserTests` failed because `--max-steps` was not captured for `melix lora train`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops_unit.py -q`
  - Result: `1 failed, 22 passed` because worker normalization did not cap computed iterations with
    `max_steps`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest tests/test_phase8_acceptance_bundle.py -q`
  - Result: `2 failed, 16 passed` because the acceptance bundle did not yet support
    `real_small_model` or explicit publish-skip metadata
- Green verification after implementation:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter MelixCLIParserTests`
  - Result: `34 tests passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter subprocessBackedLoraOperationsBuildPublicCLIArguments`
  - Result: `1 test passed`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py services/mlx-worker-python/tests/test_runtime_edges.py -q`
  - Result: `73 passed`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest tests/test_phase8_acceptance_bundle.py -q`
  - Result: `18 passed`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest tests/integration/test_phase8_cli_acceptance.py -q -k 'phase8_acceptance_bundle_closes_lora_bench_eval_and_export_paths or phase8_acceptance_bundle_real_small_model_profile_closes_real_lora_chain'`
  - Result: `1 passed, 1 skipped`
  - Skip reason: the real-model path only runs when `MELIX_PHASE8_REAL_SMALL_MODEL_PATH` points to
    a provisioned local MLX model directory
  - `make phase8-real-e2e`
  - Result: `1 passed, 6 deselected in 73.63s`
  - Run mode: real-model Hub fallback on `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`, real dataset
    training fixture `melix-dev-dataset.v1`, LoRA train plus activate plus bench plus eval plus
    export closure completed end-to-end

### Metrics Report

- `training.max_steps`: measured as explicit LoRA-train evidence in CLI arguments, worker config,
  and acceptance bundle metadata
- `runtime.activation_mode`: measured as explicit acceptance evidence and asserted to
  `adapter_backed_runtime` in the real-profile path
- `experiment.index_exists`: measured as local-first experiment evidence from
  `model-ops/train_lora/lora-experiments.index.json`
- `publish.status`: measured as explicit acceptance evidence and fixed to `disabled` for the
  `real_small_model` profile, with `publish.skip_reason=publish_disabled`

## Final Verification Gate On 2026-04-16

This handoff refresh verifies the changed scope with fresh evidence for Python coverage, Swift
changed-line coverage, and the real small-model CLI E2E before publish.

### Verification Results

- Python repository coverage:
  - `make py-coverage`
  - Result: `773 passed`
  - Coverage report total: `95%`
- Python changed-line coverage:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx coverage json -o /tmp/lora-real-python-coverage.json`
  - `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/lora-real-python-coverage.json ...`
  - Result: `96.10% (641/667)`
- Swift root changed-line coverage:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --filter "MelixCLIParserTests|MelixCLIRunnerTests/(loraListResolvesTextModelAndRendersRegistryOutput|loraTrainForwardsExpectedOperationPayload|loraDatasetInspectForwardsExpectedOperationPayload|loraDatasetBuildForwardsExpectedOperationPayload|subprocessBackedLoraOperationsBuildPublicCLIArguments|subprocessBackedModelOperationsCoverPublicModelOpsBranches|subprocessBackedEvaluationCompareSupportsRepoTargetsAndNestedResults|evalRunForwardsCustomHFDatasetSourceMappingAndProfileControls|evalCompareForwardsCustomJSONLSourceMappingAndProfileControls)"`
  - `python3 scripts/swift_changed_line_coverage.py --binary .build/arm64-apple-macosx/debug/melixPackageTests.xctest/Contents/MacOS/melixPackageTests --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata Sources/MelixCLICore/MelixCLI.swift tests/MelixCLITests/MelixCLIParserTests.swift tests/MelixCLITests/MelixCLIRunnerTests.swift`
  - Result: `92.93% (684/736)`
- Swift control-plane changed-line coverage:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/services/control-plane-swift/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter "ControlPlaneServiceTests/(executeHandlesModelListBySyncingActivatedDerivedModelsFromRegistrySnapshots|executeRegistersAdapterBackedDerivedModelsIntoTheCatalogWithCompatibilityRouting)|PythonBridgeWorkerClientTests/bootstrapWorkerPreparationPreservesAdapterBackedRuntimeMetadataForActivatedDerivedModels"`
  - `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/ModelCatalog/RegistrySnapshotSync.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`
  - Result: `100.00% (15/15)`
- Swift menubar changed-line coverage:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter "RuntimeViewModelTests/(modelInfoOpsDoctorAndBenchPopulateToolState|evaluationCompareSupportsCustomJSONLDatasetSources|loraTrainingAndActivationDispatchConfiguredPayloads|modelToolingSnapshotNormalizesPendingAdapterPayloads|loraTrainingPresetsApplyExpectedNamedDefaults|modelToolingSnapshotSkipsInvalidExperimentGroupsAndParsesStringBackedDoubles)|DesktopFoundationViewTests/(toolsWorkspaceRendersLoRATrainingControls|trainingToolSectionRendersPopulatedActivationState|toolsTabButtonsDispatchInspectDiagnosticsBenchAndModelOperations|toolsTabRendersPendingAdapterRegistryRows|toolsWorkspaceRendersGroupedLoraExperimentRecommendations)|Phase8LoRAWindowSmokeTests/phase8LoRAWindowSmokeEmitsCanonicalAcceptanceEvidence|MelixSubprocessCLIWorkflowRunnerTests/unsupportedLoraDatasetCommandsPreservePublicCommandIDs"`
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/CLI/MelixCLIWorkflowRunning.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
  - Result: `99.60% (492/494)`
- Swift aggregate changed-line coverage across the touched root, control-plane, and menubar scopes:
  - Result: `95.66% (1191/1245)`
- Real small-model LoRA E2E:
  - `make phase8-real-e2e`
  - Result: `1 passed, 6 deselected in 84.49s`
  - Run mode: real-model acceptance on `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` with the real
    dataset fixture and the full `Dataset -> Train -> Activate/Test -> Compare` closure
  - Publish evidence: explicit skip remains recorded for this acceptance profile

### Metrics Report

- Changed-scope Python coverage: measurable and above gate at `96.10% (641/667)`
- Changed-scope Swift coverage: measurable and above gate at `95.66% (1191/1245)`
- Repository Python coverage: measurable and above gate at `95%`
- Real workload evidence: measurable and refreshed with a passing real small-model E2E run
