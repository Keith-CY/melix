# Benchmark, Matrix, And Evaluation Closure Master Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining benchmark, matrix, and evaluation scope through five independently acceptable CLI-first phases, each with explicit CLI acceptance, Window UI acceptance, positive and negative UT coverage, positive and negative E2E coverage, and a squash-merge handoff into local `main`.

**Architecture:** Treat `MelixCLICore` as the single product-behavior source of truth. Implement CLI workflows first, then integrate the Window UI as a thin operator shell that invokes `melix` subprocesses in production and the same CLI workflow through a shared runner seam in tests. Execute each phase serially, squash merge it into local `main`, refresh and sync local `main`, rebase or recreate the next phase head from that refreshed base, and only then begin the next phase.

**Tech Stack:** Swift, SwiftUI, `MelixCLICore`, Swift control plane, Python model-operations worker, protobuf, file-backed benchmark and evaluation artifacts, pytest, Swift Testing, repository-owned integration harnesses.

This document is the master orchestration plan only. Before any phase enters code changes, write or
update a phase-specific implementation plan with the exact files, focused tests, CLI acceptance
steps, Window UI acceptance steps, and metrics capture for that phase.

---

### Task 1: Freeze Shared Program Rules And Test Harness Boundaries

**Files:**
- Modify: `docs/superpowers/specs/2026-04-09-benchmark-matrix-evaluation-closure-design.md`
- Modify: `docs/benchmark-evaluation-contract.md`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`
- Modify: `docs/runbooks/m7-benchmark-and-evaluation-foundation.md`
- Modify: `Sources/MelixCLICore/`
- Modify: `apps/macos-menubar/Sources/AppMain/`
- Test: `tests/MelixCLITests/`
- Test: `apps/macos-menubar/Tests/MenuBarTests/`

- [ ] Record the designated text acceptance model as `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` in the canonical contract and the operator runbooks.
- [ ] Record the designated multimodal acceptance baseline in the runbooks for image-grounded phases so multimodal acceptance stays explicit rather than implied.
- [ ] Define one shared CLI runner seam contract that matches production CLI workflow shapes closely enough for UI test injection.
- [ ] Define the production subprocess contract for the Window UI so every later phase can prove real `melix` invocation behavior without inventing a second pathway.
- [ ] Record that this master plan is orchestration-only and that every phase must begin from a phase-specific implementation plan before code changes start.
- [ ] Define the minimum phase gate checklist:
  - CLI positive UT
  - CLI negative UT
  - CLI positive E2E
  - CLI negative E2E
  - Window UI positive UT
  - Window UI negative UT
  - Window UI positive E2E
  - Window UI negative E2E
  - CLI acceptance
  - Window UI acceptance
  - metrics report
  - squash merge to local `main`
- [ ] Ensure the shared harness documentation states that Window UI production mode must invoke `melix` as a subprocess, while tests must use the runner seam unless a production-subprocess proof is specifically required.

**Verification**

- `git diff --check`
- `swift test --filter MelixCLITests`
- `swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|ControlPlaneXPCClientTests'`

**Expected evidence**

- contract and runbook text explicitly records the text acceptance model and the mixed UI execution rules
- test targets still compile after the shared seam or subprocess abstractions are introduced or renamed

### Task 2: Phase 1 Baseline CLI-First Closure

**Files:**
- Modify: `docs/plans/2026-04-07-real-mlx-benchmark-and-evaluation.md`
- Modify: `docs/benchmark-evaluation-contract.md`
- Modify: `docs/runbooks/m7-benchmark-and-evaluation-foundation.md`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift`
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `services/mlx-worker-python/worker/productization/benchmark_export.py`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Test: `tests/MelixCLITests/`
- Test: `services/control-plane-swift/Tests/ControlPlaneTests/`
- Test: `services/mlx-worker-python/tests/`
- Test: `apps/macos-menubar/Tests/MenuBarTests/`
- Test: `tests/integration/`

- [ ] Make live-evidence benchmark and evaluation paths truthful for the existing `bench`, `bench matrix`, and `eval` workflows.
- [ ] Ensure CLI command behavior is the source of truth for standard benchmark, matrix benchmark, evaluation, and export behavior.
- [ ] Add or tighten CLI positive UT for:
  - `bench run`
  - `bench list`
  - `bench export-csv`
  - `bench matrix run`
  - `bench matrix list`
  - `bench matrix export-summary-csv`
  - `bench matrix export-requests-csv`
  - `eval run`
  - `eval list`
  - `eval export-summary-csv`
  - `eval export-samples-csv`
  - `eval export-samples-jsonl`
- [ ] Add or tighten CLI negative UT for:
  - conflicting targets
  - unsupported task kinds
  - invalid matrix dimensions
  - missing output paths
  - unavailable benchmark or evaluation targets
  - malformed export-bundle decoding
- [ ] Add CLI positive E2E against `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` for:
  - one standard benchmark
  - one matrix benchmark
  - one evaluation run
  - one export flow
- [ ] Add CLI negative E2E for:
  - invalid matrix load-budget combinations
  - unsupported evaluation target resolution
  - missing persisted job export
  - live-runtime worker failure surfacing
- [ ] Refactor the Window UI benchmark and evaluation surfaces so they invoke CLI workflows through the shared runner seam in tests and through `melix` subprocesses in production.
- [ ] Add Window UI positive UT for benchmark, matrix, evaluation, and export state rebuilding from CLI-owned outputs.
- [ ] Add Window UI negative UT for invalid input guards, seam failures, malformed outputs, and subprocess launch failures.
- [ ] Add Window UI positive E2E for:
  - run benchmark
  - run matrix benchmark
  - run evaluation
  - export benchmark and evaluation artifacts
- [ ] Add Window UI negative E2E for:
  - blocked invalid form combinations
  - CLI failure rendering
  - subprocess failure rendering
- [ ] Add at least one production-mode subprocess proof for the existing benchmark or evaluation surface so the product path is not validated only through the seam.
- [ ] Produce phase-scoped metrics and acceptance notes, then squash merge the phase to local `main`, refresh and sync local `main`, and rebase or recreate the next phase head from that refreshed base.

**Verification**

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_benchmark_export.py -q`
- `swift test --filter MelixCLITests`
- `swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|BenchmarkExportBundleTests'`
- `swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|ControlPlaneXPCClientTests'`
- `make integration-test`

**Expected evidence**

- the baseline benchmark, matrix, and evaluation workflows produce live MLX evidence where the product claims live execution
- the Window UI surfaces visibly consume CLI-owned workflow outputs rather than parallel in-app logic

### Task 3: Phase 2 Multimodal Evaluation And VLM Benchmark Closure

**Files:**
- Modify: `docs/plans/2026-04-07-multimodal-evaluation-and-lora-comparison-roadmap.md`
- Modify: `docs/plans/2026-03-30-m7-8-vlm-benchmark-options.md`
- Modify: `docs/benchmark-evaluation-contract.md`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`
- Modify: `services/mlx-worker-python/fixtures/evaluation/`
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Add: `services/mlx-worker-python/worker/productization/evaluation_suites.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Modify: `services/mlx-worker-python/worker/productization/benchmark_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/benchmark_suites.py`
- Modify: `services/control-plane-swift/Sources/XPCService/BenchmarkExportBundle.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Test: `services/mlx-worker-python/tests/`
- Test: `services/control-plane-swift/Tests/ControlPlaneTests/`
- Test: `tests/MelixCLITests/`
- Test: `apps/macos-menubar/Tests/MenuBarTests/`
- Test: `tests/integration/`

- [ ] Close the multimodal evaluation contract so image-grounded suites are first-class `eval` workflows rather than partial worker-only behavior.
- [ ] Close VLM benchmark inputs and outputs so image-aware benchmark jobs preserve image-source or scenario identity and fail honestly on unsupported combinations.
- [ ] Keep benchmark and evaluation export decoding aligned with the new multimodal evidence fields so CLI and Window UI both render media-aware outputs from the same bundle contract.
- [ ] Add CLI positive UT for multimodal evaluation and VLM benchmark parsing, normalization, export, and history rendering.
- [ ] Add CLI negative UT for:
  - unsupported multimodal target families
  - text-backed multimodal targets
  - invalid multimodal dataset or task-kind pairings
  - unsupported matrix task families
- [ ] Add CLI positive E2E for:
  - one image-grounded evaluation run against the designated multimodal baseline
  - one VLM-capable benchmark run
  - one multimodal export flow with media-backed sample evidence
- [ ] Add CLI negative E2E for:
  - invalid multimodal target import
  - text-backed VLM evaluation rejection
  - invalid VLM benchmark matrix request rejection
- [ ] Integrate multimodal benchmark and evaluation behaviors into the existing Window UI benchmark and evaluation surfaces through the CLI seam and subprocess path.
- [ ] Add Window UI positive UT and E2E for multimodal configuration, result presentation, sample preview, and export.
- [ ] Add Window UI negative UT and E2E for multimodal guard rails and failure-state rendering.
- [ ] Add at least one production-mode subprocess proof for a multimodal UI workflow.
- [ ] Produce phase-scoped metrics and acceptance notes, then squash merge the phase to local `main`, refresh and sync local `main`, and rebase or recreate the next phase head from that refreshed base.

**Verification**

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_schemas.py services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_benchmark_schemas.py services/mlx-worker-python/tests/test_benchmark_suites.py -q`
- `swift test --filter MelixCLITests`
- `swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|BenchmarkExportBundleTests'`
- `swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
- `make integration-test`

**Expected evidence**

- at least one image-grounded evaluation path and one VLM benchmark path are accepted products, not just worker experiments

### Task 4: Phase 3 Comparison And Raw Export Closure

**Files:**
- Modify: `docs/plans/2026-03-30-m7-7-result-export-and-comparison-tables.md`
- Modify: `docs/plans/2026-04-07-multimodal-evaluation-and-lora-comparison-roadmap.md`
- Modify: `docs/benchmark-evaluation-contract.md`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`
- Add: `services/mlx-worker-python/worker/productization/evaluation_compare.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/benchmark_export.py`
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `services/control-plane-swift/Sources/XPCService/BenchmarkExportBundle.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Test: `services/mlx-worker-python/tests/`
- Test: `services/control-plane-swift/Tests/ControlPlaneTests/`
- Test: `tests/MelixCLITests/`
- Test: `apps/macos-menubar/Tests/MenuBarTests/`
- Test: `tests/integration/`

- [ ] Add comparison as a first-class CLI workflow for base-versus-derived evaluation rather than a manual serial operator convention.
- [ ] Add raw JSON export closure for persisted benchmark, matrix, evaluation, and comparison artifacts.
- [ ] Add CLI positive UT for comparison-job normalization, paired export rendering, raw JSON export, and regression summary rendering.
- [ ] Add CLI negative UT for:
  - malformed comparison manifests
  - missing base targets
  - invalid derived target lists
  - incompatible suite bundles
  - missing persisted component runs
- [ ] Add CLI positive E2E for:
  - one text comparison bundle using the designated text baseline model plus an activated derived model
  - one raw export workflow
  - one paired sample export flow
- [ ] Add CLI negative E2E for:
  - missing component evaluation run references
  - inconsistent comparison configuration
  - export request for an unknown comparison job
- [ ] Add an independent Window UI comparison workflow that invokes the CLI comparison path instead of embedding comparison semantics directly in SwiftUI.
- [ ] Add Window UI positive UT and E2E for comparison setup, result viewing, paired export actions, and regression-summary inspection.
- [ ] Add Window UI negative UT and E2E for invalid comparison setup, CLI failures, and subprocess failures.
- [ ] Add at least one production-mode subprocess proof for the independent comparison UI.
- [ ] Produce phase-scoped metrics and acceptance notes, then squash merge the phase to local `main`, refresh and sync local `main`, and rebase or recreate the next phase head from that refreshed base.

**Verification**

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_benchmark_export.py services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_maintenance_service.py -q`
- `swift test --filter MelixCLITests`
- `swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|BenchmarkExportBundleTests'`
- `swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
- `make integration-test`

**Expected evidence**

- comparison is independently operable from both CLI and a dedicated Window UI workflow
- raw export is preserved as a productized capability rather than a worker-only helper

### Task 5: Phase 4 Semantic Evaluation Controls And Executable Code Evaluation

**Files:**
- Modify: `docs/plans/2026-04-07-multimodal-evaluation-and-lora-comparison-roadmap.md`
- Modify: `docs/benchmark-evaluation-contract.md`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`
- Add: `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Test: `services/mlx-worker-python/tests/`
- Test: `services/control-plane-swift/Tests/ControlPlaneTests/`
- Test: `tests/MelixCLITests/`
- Test: `apps/macos-menubar/Tests/MenuBarTests/`
- Test: `tests/integration/`

- [ ] Make `few_shot`, `seed`, `scoring_mode`, and `code_exec_policy` active controls instead of metadata-only fields.
- [ ] Add executable code scoring for `humaneval` and `mbpp`.
- [ ] Add CLI positive UT for:
  - control normalization
  - scorer selection
  - code-eval result export
  - code-eval diagnostics rendering
- [ ] Add CLI negative UT for:
  - unsupported scoring modes
  - invalid code execution policies
  - blocked code execution for unsupported suites
  - timeout or execution-failure mapping
- [ ] Add CLI positive E2E for:
  - one control-sensitive non-code evaluation run that proves the controls affect execution
  - one `humaneval` or `mbpp` run that produces real code-execution evidence
- [ ] Add CLI negative E2E for:
  - invalid code execution policy rejection
  - timed-out or failed code execution evidence
  - unsupported scorer rejection
- [ ] Integrate the new evidence and control-state presentation into the existing Window UI evaluation surface through the CLI seam and subprocess path.
- [ ] Add Window UI positive UT and E2E for control-state rendering, code-exec result rendering, and exported sample diagnostics.
- [ ] Add Window UI negative UT and E2E for blocked policies, code-eval failures, and subprocess errors.
- [ ] Add at least one production-mode subprocess proof for the Window UI code-exec evaluation path.
- [ ] Produce phase-scoped metrics and acceptance notes, then squash merge the phase to local `main`, refresh and sync local `main`, and rebase or recreate the next phase head from that refreshed base.

**Verification**

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_maintenance_service.py -q`
- `swift test --filter MelixCLITests`
- `swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests`
- `swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
- `make integration-test`

**Expected evidence**

- `humaneval` and `mbpp` no longer rely on synthetic success behavior for evidence-bearing evaluation
- evaluation controls change real execution or scoring behavior and fail honestly when unsupported

### Task 6: Phase 5 Statistical Reporting And Release-Gate Closure

**Files:**
- Modify: `docs/plans/2026-03-30-m7-10-benchmark-and-eval-release-gates.md`
- Modify: `docs/plans/2026-04-07-multimodal-evaluation-and-lora-comparison-roadmap.md`
- Modify: `docs/benchmark-evaluation-contract.md`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`
- Modify: `docs/runbooks/m7-benchmark-and-evaluation-foundation.md`
- Add: `services/mlx-worker-python/worker/productization/evaluation_reports.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Modify: `services/mlx-worker-python/worker/productization/release_gates.py`
- Modify: `infra/release/`
- Modify: `scripts/`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Test: `services/mlx-worker-python/tests/`
- Test: `services/control-plane-swift/Tests/ControlPlaneTests/`
- Test: `tests/MelixCLITests/`
- Test: `apps/macos-menubar/Tests/MenuBarTests/`
- Test: `tests/integration/`

- [ ] Add release-style reporting for benchmark, evaluation, and comparison outputs with explicit improvement or regression or inconclusive semantics.
- [ ] Add confidence interval or bootstrap reporting where the contract requires uncertainty evidence.
- [ ] Feed benchmark and evaluation outputs into release-gate automation using persisted repository-owned artifacts.
- [ ] Add CLI positive UT for:
  - report generation
  - release-gate verdict rendering
  - confidence interval export
  - threshold policy decoding
- [ ] Add CLI negative UT for:
  - malformed gate inputs
  - missing artifacts
  - insufficient evidence for a verdict
  - conflicting gate thresholds
- [ ] Add CLI positive E2E for:
  - one release-style report generation flow
  - one gate pass flow
  - one gate fail flow
- [ ] Add CLI negative E2E for:
  - inconclusive evidence flow
  - missing artifact gate failure
  - malformed threshold policy rejection
- [ ] Add an independent Window UI release-gate workflow that invokes the CLI-owned release-gate path.
- [ ] Add Window UI positive UT and E2E for report inspection, gate verdict rendering, and threshold display.
- [ ] Add Window UI negative UT and E2E for inconclusive outcomes, gate failures, CLI failures, and subprocess failures.
- [ ] Add at least one production-mode subprocess proof for the independent release-gate UI.
- [ ] Produce phase-scoped metrics and acceptance notes, then squash merge the phase to local `main`, refresh and sync local `main`, and rebase or recreate the next phase head from that refreshed base.

**Verification**

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_release_gates.py -q`
- `swift test --filter MelixCLITests`
- `swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|BenchmarkExportBundleTests'`
- `swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
- `make phase8-release-gate`
- `make integration-test`

**Expected evidence**

- release gates become first-class benchmark and evaluation consumers
- release-style evidence is visible from both CLI and a dedicated Window UI workflow

### Task 7: Final Program Verification And Safe Exit

**Files:**
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`
- Modify: `docs/runbooks/m7-benchmark-and-evaluation-foundation.md`
- Modify: `README.md`
- Modify: `docs/benchmark-evaluation-contract.md`
- Modify: `docs/plans/2026-03-30-full-capability-roadmap-execution-index.md`

- [ ] After Phase 5, run the full repository verification expected for the touched benchmark, matrix, and evaluation scope.
- [ ] Ensure the final docs describe:
  - the designated text acceptance model
  - the designated multimodal acceptance model
  - CLI-first ownership
  - Window UI mixed execution model
  - phase-complete operator workflows
  - release-gate operator workflows
- [ ] Ensure every phase left explicit notes that it was squash merged into local `main`.
- [ ] If any phase cannot clear its gate, stop the program without beginning the next phase.

**Verification**

- `make proto`
- `make py-test`
- `make swift-test`
- `make integration-test`

**Expected evidence**

- the benchmark, matrix, and evaluation closure program has a final repo-wide verification record
- documentation matches the accepted product behavior instead of the pre-closure partial state
