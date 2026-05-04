# Issue 347 Desktop LoRA Training Studio

## Goal

Turn the Window UI LoRA workflow into a desktop training-studio v1 where
operators can persist complete training configurations as named jobs, reload or
clone them later, rerun them without re-entry, and carry completed artifacts
forward into existing activation and post-training surfaces.

## Source

- GitHub issue: https://github.com/Keith-CY/melix/issues/347
- Operator runbook: `docs/runbooks/phase-8-lora-adapter-workflow.md`
- Existing experiment surface: `docs/plans/2026-04-21-lora-experiment-surfaces.md`
- Existing training mode contract:
  `docs/plans/2026-05-03-issue-15-lora-training-mode-expansion.md`

## Scope

- Add a repository-owned desktop LoRA job/config schema persisted under
  `MELIX_HOME/state`.
- Persist desktop-created draft and training job records with config, status,
  timestamps, output path, manifest path, latest output text, and follow-up
  artifact paths.
- Add Window UI actions to save the current form, load/edit a non-running job,
  duplicate, rerun, cancel a non-running job record, and delete records.
- Add import/export of the stable config schema so a saved setup can round-trip
  through a reusable file.
- Add a saved-job detail surface that exposes terminal state, latest output, and
  next-step affordances for activation, quantization, conversion, benchmark,
  evaluation, and adapter publish workflows using existing Melix commands and
  UI sections.

## Non-Goals

- Replace CLI or control-plane model operation execution authority.
- Add scheduler/runtime changes or a new Python-managed bootstrap layer.
- Implement streaming process cancellation for an already-running trainer.
- Add new LoRA algorithms or trainer loops.

## Design

- Store all desktop job state in `MELIX_HOME/state/lora-training-jobs.json`.
- Export individual reusable configs as
  `melix.desktop_lora_training_config.v1`; the internal job store uses
  `melix.desktop_lora_training_jobs.v1`.
- Keep the config shape close to the existing SwiftUI form fields so import,
  duplicate, load, and rerun are lossless for all supported desktop LoRA inputs.
- Treat the saved job id as the desktop orchestration identity. Backend
  `train_lora` job ids remain execution receipts and are stored as
  `last_run_job_id` when available.
- For command authority, rerun calls the existing `trainPrimaryModel()` path
  after loading the saved config into the form. Activation, publish, quantize,
  convert, benchmark, and evaluation follow-up actions select or route existing
  UI/command surfaces instead of inventing new execution paths.
- Treat list selection as inspection-only until the operator explicitly loads,
  duplicates, reruns, imports, or saves a draft from the current form. This
  prevents a startup-selected saved job from being overwritten by a default form.
- Decode saved job records lossily within a supported jobs document so one
  future-version or corrupt record does not prevent every other saved job from
  loading.
- Serialize LoRA job store read-modify-write operations at the store boundary so
  concurrent desktop actions cannot lose updates in the shared JSON file.

## Performance And Metrics

- Persistence is a single small JSON file loaded at view-model startup and
  rewritten atomically after desktop job mutations.
- Store mutation determinism is measured by concurrent draft creation retaining
  every saved job id and config.
- UI selection determinism is measured by saved-job list selection and
  quantization-profile selection both notifying state changes, while selection
  alone cannot overwrite a saved job that has not been explicitly loaded.
- Success metrics:
  - 100 percent of desktop LoRA training launches create or update a saved job
    record before execution starts.
  - Rerun and duplicate preserve all supported desktop LoRA form fields.
  - Import/export round-trip preserves all supported LoRA config fields.
  - The selected saved job detail exposes terminal status, latest output, and
    next-step actions without opening raw JSON.

## Verification

- Add MelixCLICore store tests for schema persistence, duplicate/edit/delete,
  and config import/export round-trip.
- Add RuntimeViewModel tests for save/load/rerun/cancel/delete job actions and
  training-result persistence.
- Add view rendering tests that prove the Training workspace exposes `Saved
  Jobs`, job detail text, and follow-up action labels.
- Run targeted Swift tests for the touched CLI core and menubar suites.
- Run changed-scope coverage or an explicit N/A metrics report if this Swift UI
  slice has no reliable changed-line coverage gate.

## Verification Results

- `make swift-test` passed.
- `xcrun swift test --enable-code-coverage --filter LoraTrainingJobStoreTests`
  passed 8 tests.
- `xcrun swift test --package-path apps/macos-menubar --enable-code-coverage
  --filter <issue-347 RuntimeViewModel/DesktopFoundationView/AppMainBootstrap
  focused filter>` passed 23 tests.
- Root changed-line coverage:
  - `Sources/MelixCLICore/MelixHome.swift`: 100.00% (1/1)
  - `Sources/MelixCLICore/LoraTrainingJobStore.swift`: 100.00% (252/252)
  - `tests/MelixCLITests/LoraTrainingJobStoreTests.swift`: 100.00% (193/193)
  - Total: 100.00% (446/446)
- macOS menubar changed-line coverage:
  - `AppMain.swift`: 100.00% (3/3)
  - `LoraTrainingJobStoreAdapter.swift`: 100.00% (37/37)
  - `RuntimeViewModel.swift`: 98.04% (651/664)
  - `DesktopWorkspaceShellView.swift`: 87.93% (306/348)
  - `AppMainBootstrapTests.swift`: 100.00% (41/41)
  - `DesktopFoundationViewTests.swift`: 100.00% (89/89)
  - `RuntimeViewModelTests.swift`: 100.00% (637/637)
  - `TestSupport.swift`: 100.00% (85/85)
  - Total: 97.11% (1849/1904)
- Review follow-up verification:
  - `swift test --enable-code-coverage --filter LoraTrainingJobStoreTests`
    passed 10 tests.
  - `swift test --package-path apps/macos-menubar --scratch-path
    /private/tmp/melix-menubar-review-build --enable-code-coverage --filter
    "lora|Lora|LoRA|quantizeActionStoresTypedQuantizationSummary|downloadsSectionExposesSavedLoRAPackagingTarget"`
    passed 37 tests.
  - `git diff --check` passed.
- Review follow-up changed-line coverage:
  - Root LoRA store scope: 100.00% (140/140).
  - macOS menubar review scope: 98.29% (115/117).
- Post-review CI stabilization verification:
  - `swift test --package-path apps/macos-menubar --enable-code-coverage
    --filter localServerCreationRefreshesReadyModelOptionsFromRegistryWhenCatalogIsEmpty`
    passed 1 test.
  - `swift test --package-path apps/macos-menubar --enable-code-coverage
    --filter "RuntimeViewModelTests|DesktopFoundationViewTests"`
    passed 420 tests.
  - `make swift-test` passed.
  - `git diff --check` passed.
- Post-review CI stabilization changed-line coverage:
  - macOS menubar review scope: 97.10% (1705/1756).
