# Multimodal Evaluation And LoRA Comparison Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prioritize Melix evaluation expansion so the product can prove multimodal model quality first, LoRA-derived model deltas second, and then close the remaining evidence gaps in scoring semantics, code execution, and reporting.

**Architecture:** Keep `melix eval` as the single product surface for intelligence-style measurement across CLI, control plane, worker execution, and persisted exports. Extend that path so multimodal inputs, paired comparison runs, and suite-level evidence are first-class protocol and storage concepts rather than manual operator conventions. Swift remains orchestration truth for target resolution and job history, while the Python worker remains execution and scoring truth.

**Tech Stack:** Swift, SwiftUI, Python, protobuf, MLX runtimes, repository-owned evaluation fixtures, CSV and JSONL export bundles, pytest, Swift Testing.

---

## Current State

- `eval` currently proves fixed-suite correctness for `text-generation` targets only.
- Persisted evaluation summaries and sample-level exports already exist, so the product has an evidence storage foundation.
- Multimodal evaluation is not implemented yet even though the shared task taxonomy already includes `image-to-text` and `image-text-to-text`.
- LoRA comparison is possible today only as a manual serial workflow against activated derived `--model-id` targets.
- `few_shot`, `seed`, `scoring_mode`, and `code_exec_policy` are mostly recorded as metadata today rather than fully enforced runtime or scoring semantics.
- `humaneval` and `mbpp` currently do not prove true code-execution correctness.

## Priority Order

1. Multimodal evaluation support
2. LoRA comparison testing
3. Semantic evaluation controls
4. Executable code evaluation
5. Statistical evidence and reporting

## Evidence Model

Evaluation should let Melix prove the following claims:

- Under one fixed suite, render path, and scoring policy, one target outperforms another target.
- A LoRA-derived model improves in-domain quality without hiding regressions on general suites.
- A multimodal-capable model can answer media-grounded tasks with persisted per-sample evidence.
- Operators can inspect sample-level predictions, parse outcomes, and failure cases instead of only reading one summary score.

Evaluation must not claim the following:

- absolute model intelligence
- serving performance or latency quality
- cross-dataset generalization beyond the selected suite bundle
- production robustness or safety outside the measured tasks

## Success Metrics And Probes

Existing cross-cutting probes that remain required:

- `eval.<suite>.score_value`
- `eval.<suite>.correct_count`
- `eval.<suite>.incorrect_count`
- `eval.<suite>.duration_seconds`
- per-sample `parse_status`
- per-sample `time_s`

New probes required by this roadmap:

- `eval.<suite>.multimodal_preprocess_ms`
- `eval.<suite>.paired_delta`
- `eval.<suite>.paired_win_count`
- `eval.<suite>.paired_loss_count`
- `eval.<suite>.regression_count`
- `eval.<suite>.code_exec_pass_count`
- `eval.<suite>.code_exec_fail_count`
- `eval.<suite>.confidence_interval_low`
- `eval.<suite>.confidence_interval_high`

## Milestones

### Milestone 1: Multimodal Evaluation Foundation

**Outcome**

- `melix eval` can run vision-grounded suites as a first-class product path.

**Scope**

- Extend `eval` beyond `text-generation`.
- Start with the existing task kinds:
  - `image-to-text`
  - `image-text-to-text`
- Add repository-owned multimodal fixture packaging with stable media references and expected-answer fields.
- Persist media identity, task kind, raw prediction, parsed prediction, and scorer metadata per sample.
- Keep audio and video evaluation explicitly deferred until image-grounded evaluation is stable.

**Primary files**

- Modify: `docs/benchmark-evaluation-contract.md`
- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
- Modify: `packages/protocol/schema/worker/v1/common.proto`
- Modify: `packages/protocol/schema/worker/v1/inference.proto`
- Modify: `packages/protocol/schema/worker/v1/maintenance.proto`
- Add: `services/mlx-worker-python/worker/productization/evaluation_suites.py`
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Modify: `services/mlx-worker-python/fixtures/evaluation/*`
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`

**Exit criteria**

- At least one repository-owned multimodal suite runs end to end against a VLM-capable model.
- Sample export rows include task kind, input modalities, and media-backed evidence fields.
- CLI and Window UI distinguish text-only evaluation from multimodal evaluation.

**Risks**

- fixture size and media storage policy
- preserving comparability across task types
- keeping image ingress identical between evaluation and live runtime execution

### Milestone 2: LoRA Comparison Workflow

**Outcome**

- Base-model versus derived-model comparison becomes a first-class evaluation workflow instead of a manual operator procedure.

**Scope**

- Add a comparison manifest with one base target, one fixed suite bundle, one fixed configuration, and one or more derived targets.
- Keep execution serial in v1 and require explicit unload or teardown between compared targets.
- Persist paired outputs:
  - suite-level deltas
  - paired sample rows
  - win or loss or tie counts
  - regression summary rows
- Support two comparison bundle types:
  - in-domain improvement bundles
  - regression guard bundles

**Primary files**

- Modify: `docs/benchmark-evaluation-contract.md`
- Add: `services/mlx-worker-python/worker/productization/evaluation_compare.py`
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`

**Exit criteria**

- One product path can compare a base model and multiple activated derived models under the same suite and control set.
- Persisted outputs show per-suite delta, paired sample evidence, and explicit regression counts.
- Operator workflow stays target-based by using derived `model_id` values rather than raw adapter paths.

**Risks**

- runtime teardown between serial runs
- preserving identical ordering and sampling across compared targets
- keeping derived-model catalog identity stable across repeated comparison jobs

### Milestone 3: Semantic Evaluation Controls

**Outcome**

- Evaluation control fields affect real execution and scoring behavior instead of acting as metadata-only annotations.

**Scope**

- Make `few_shot` affect prompt construction.
- Make `seed` control sampling or ordering where supported and persist the effective seed used.
- Make `scoring_mode` select real scorer implementations instead of only renaming summary fields.
- Make `code_exec_policy` gate code-execution behavior or explicit rejection when unsupported.
- Remove synthetic fallback from default success paths or mark it as non-evidence output.

**Primary files**

- Modify: `docs/benchmark-evaluation-contract.md`
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`

**Exit criteria**

- Requested control values produce observable execution or scoring changes.
- Invalid control combinations fail fast.
- Persisted artifacts record both requested and effective control values.

**Risks**

- backend determinism differences across model families
- suite-specific scorer drift
- accidental backwards compatibility breakage for existing exports

### Milestone 4: Executable Code Evaluation

**Outcome**

- Code suites produce evidence from running candidate code under policy rather than text matching or synthetic success paths.

**Scope**

- Add a safe code-execution harness for `humaneval` and `mbpp`.
- Persist compile status, runtime status, timeout status, and test outcome details.
- Tie execution behavior to `code_exec_policy`.
- Keep `pass_at_1` as the initial code-evaluation metric unless the contract is explicitly widened later.

**Primary files**

- Modify: `docs/benchmark-evaluation-contract.md`
- Add: `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`

**Exit criteria**

- `humaneval` and `mbpp` no longer rely on text-match substitution for success.
- Sample exports include execution status and failure evidence.
- `code_exec_policy` is enforceable and visible in stored results.

**Risks**

- sandbox safety
- timeout and resource isolation policy
- reproducibility across local environments

### Milestone 5: Statistical Evidence And Reporting

**Outcome**

- Evaluation becomes strong enough for release-style go or no-go decisions instead of raw score snapshots only.

**Scope**

- Add category or subject breakdowns where the suite supports them.
- Add paired-delta summaries and regression thresholds.
- Add confidence intervals or bootstrap estimates for comparison reports.
- Add operator-facing Markdown or CSV summary bundles for release reviews and milestone gates.

**Primary files**

- Modify: `docs/benchmark-evaluation-contract.md`
- Add: `services/mlx-worker-python/worker/productization/evaluation_reports.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`

**Exit criteria**

- Comparison reports can classify outcomes as improvement, regression, or inconclusive.
- Operators can export suite summaries, paired sample evidence, and release-friendly reports from one job family.
- Release gates can consume persisted thresholds without bespoke scripts.

**Risks**

- false confidence from small sample sizes
- confusing report surfaces if raw and statistical outputs are mixed poorly
- suite coverage gaps for unsupported categories

## Cross-Milestone Plan

1. Establish the canonical multimodal and paired-comparison contract first.
2. Ship one image-grounded evaluation path before broadening to more modalities.
3. Make LoRA comparison reuse persisted evaluation artifacts rather than creating a new benchmark-only workflow.
4. Make control fields semantically real before using them for gating evidence.
5. Add executable code scoring before claiming code-suite quality.
6. Add statistical reporting only after the underlying evidence path is trustworthy.

## Executable Work Packages

### Work Package 1: Reset Contract And Evaluation Taxonomy

**Objective**

- Align the canonical contract with the next evaluation scope before code changes begin.

**Files**

- Modify: `docs/benchmark-evaluation-contract.md`
- Modify: `docs/plans/2026-04-03-benchmark-evaluation-redesign.md`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`

- [ ] Define the v2 evaluation scope in the contract:
  - multimodal task kinds
  - paired comparison vocabulary
  - evidence claims and non-claims
- [ ] Define the initial comparison bundle types:
  - in-domain bundle
  - regression bundle
- [ ] Mark current text-only `eval` behavior as v1 rather than the long-term contract ceiling.

**Verification**

- `git diff --check`

### Work Package 2: Add Multimodal Fixture Packaging

**Objective**

- Create a repository-owned fixture format that can describe media-backed evaluation samples without ad hoc loader logic.

**Files**

- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/fixtures/evaluation/*`
- Modify: `services/mlx-worker-python/tests/test_evaluation_schemas.py`

- [ ] Extend dataset package manifests with task kind and media-awareness metadata.
- [ ] Add one vision-grounded fixture family under `services/mlx-worker-python/fixtures/evaluation/`.
- [ ] Add schema tests that preserve dataset identity, media identity, and task kind fields.

**Verification**

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_schemas.py -q`

### Work Package 3: Extend Protocol And Persistence Surfaces

**Objective**

- Make multimodal evaluation and comparison artifacts representable across protocol, worker storage, and exports.

**Files**

- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
- Modify: `packages/protocol/schema/worker/v1/common.proto`
- Modify: `packages/protocol/schema/worker/v1/inference.proto`
- Modify: `packages/protocol/schema/worker/v1/maintenance.proto`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`

- [ ] Add normalized fields for multimodal task kind, media-backed sample evidence, and paired comparison metadata.
- [ ] Keep additive schema evolution only.
- [ ] Regenerate committed protocol outputs.

**Verification**

- `make proto`
- `swift build --package-path packages/protocol/swift`

### Work Package 4: Implement Multimodal Evaluation Execution

**Objective**

- Run one image-grounded evaluation path through the live runtime and persist sample-level evidence.

**Files**

- Add: `services/mlx-worker-python/worker/productization/evaluation_suites.py`
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Modify: `services/mlx-worker-python/tests/test_evaluation_core.py`

- [ ] Load multimodal fixtures through one shared suite loader.
- [ ] Reuse the existing vision-capable runtime ingress for `image-to-text` and `image-text-to-text`.
- [ ] Persist media-backed sample rows with raw response, parsed response, and parse status.
- [ ] Add scorer coverage for exact match, normalized match, and multiple-choice style multimodal tasks.

**Verification**

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_evaluation_store.py -q`

### Work Package 5: Expose Multimodal Evaluation In CLI And Window UI

**Objective**

- Make multimodal evaluation operator-visible without creating a second product surface.

**Files**

- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`

- [ ] Extend `melix eval run` so multimodal-capable targets resolve to supported task kinds.
- [ ] Surface multimodal suite metadata in evaluation history and export flows.
- [ ] Keep UI language explicit about text-only versus multimodal suite selection.

**Verification**

- `swift test --filter MelixCLITests`
- `swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests`
- `swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests`

### Work Package 6: Implement Serial LoRA Comparison Orchestration

**Objective**

- Turn manual base-versus-derived evaluation into a persisted comparison job family.

**Files**

- Add: `services/mlx-worker-python/worker/productization/evaluation_compare.py`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`

- [ ] Add comparison job normalization with one base target and one or more derived targets.
- [ ] Keep target execution serial and unload runtime state between targets.
- [ ] Preserve one fixed suite bundle, sample ordering, and control set across the compared targets.
- [ ] Persist one comparison bundle that references the component evaluation runs.

**Verification**

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_maintenance_service.py -q`
- `swift test --filter MelixCLITests`

### Work Package 7: Add Paired Exports And Regression Reports

**Objective**

- Make LoRA comparison evidence readable and exportable without post-processing scripts.

**Files**

- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`

- [ ] Export per-suite delta rows.
- [ ] Export paired sample rows with expected answer, base prediction, derived prediction, and winner classification.
- [ ] Export regression-summary rows for the configured regression bundle.

**Verification**

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_store.py -q`
- `swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests`

### Work Package 8: Make Evaluation Controls Semantically Real

**Objective**

- Ensure operators can trust `few_shot`, `seed`, `scoring_mode`, and `code_exec_policy` as active controls.

**Files**

- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/tests/test_evaluation_core.py`

- [ ] Apply `few_shot` to prompt assembly.
- [ ] Apply `seed` to fixture ordering and any supported sampling controls.
- [ ] Route `scoring_mode` into real scorer selection.
- [ ] Reject unsupported `code_exec_policy` combinations explicitly.
- [ ] Remove default synthetic-success behavior from evidence-bearing paths.

**Verification**

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py -q`

### Work Package 9: Add Executable Code Evaluation

**Objective**

- Make code-suite outputs evidence-bearing enough for `humaneval` and `mbpp`.

**Files**

- Add: `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/tests/test_evaluation_core.py`

- [ ] Execute candidate code under policy instead of text matching.
- [ ] Persist execution diagnostics and pass or fail evidence.
- [ ] Keep `pass_at_1` as the initial scored metric.

**Verification**

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_maintenance_service.py -q`

### Work Package 10: Add Statistical Reporting And Release Gates

**Objective**

- Turn evaluation output into release-friendly evidence rather than raw score snapshots only.

**Files**

- Add: `services/mlx-worker-python/worker/productization/evaluation_reports.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`
- Modify: `docs/runbooks/m7-benchmark-and-evaluation-foundation.md`

- [ ] Add category or subject breakdown export where supported.
- [ ] Add paired confidence intervals or bootstrap estimates.
- [ ] Add release-gate summary output that can say improvement, regression, or inconclusive.
- [ ] Document the operator workflow for multimodal and LoRA comparison evidence reviews.

**Verification**

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_store.py -q`
- `git diff --check`

## Final Verification

- `make proto`
- `make py-test`
- `make swift-test`
- `make integration-test`

## Acceptance

- Melix supports at least one vision-grounded evaluation path as a first-class `eval` workflow.
- Melix supports first-class serial LoRA comparison using activated derived model IDs and shared evaluation bundles.
- Evaluation controls represent real execution or scoring behavior rather than metadata-only recording.
- `humaneval` and `mbpp` use executable code scoring.
- Operators can export summary, sample, paired-comparison, and release-style evidence from persisted results.
