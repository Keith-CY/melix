# Phase 8 Desktop Productization, Packaging, and Release Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Melix from an engineering runtime into a shippable local product with a robust operator shell, diagnostics, packaging, startup and recovery automation, and release-quality benchmark and smoke gates.

**Architecture:** Melix keeps the Swift control plane as the product orchestration core, evolves the macOS menu bar app from a minimal operator shell into a richer desktop control surface, and adds packaging, launch, diagnostics, and release infrastructure around the already-stabilized runtime layers. Productization is layered on top of prior backend support rather than used to compensate for missing runtime behavior.

**Tech Stack:** Swift 6, SwiftUI or AppKit surfaces in the existing macOS app workspace, Swift Package Manager, shell scripts, launchd assets, signing and packaging assets, XCTest, integration tests, benchmark and smoke scripts, release runbooks.

---

## Goal

Deliver a production-shaped Phase 8 implementation that upgrades the desktop operator surface, adds repeatable boot and recovery workflows, formalizes packaging and release artifacts, and introduces benchmark plus smoke gates for release candidates.

## Non-Goals

- Invent new model families or runtime capabilities that belong to earlier phases.
- Replace the native operator shell with a separate web-first admin surface.
- Treat packaging and signing as one-off manual release steps.
- Ship a glossy UI for backend features that still lack stable runtime support.
- Relax benchmark or smoke gates just to make release packaging easier.

## Context

- Relevant specs:
  - `docs/architecture-spec.md`
  - `docs/repo-skeleton.md`
  - `docs/phase-roadmap.md`
  - `docs/plans/2026-03-27-phase-7-image-generation-editing.md`
- Relevant code paths:
  - `apps/macos-menubar`
  - `services/control-plane-swift`
  - `scripts`
  - `tests/integration`
  - `docs/runbooks`
  - future packaging assets under `infra/` or other canonical repository locations defined during implementation
- Current constraints:
  - The menu bar app remains an operator shell rather than a full product dashboard.
  - Local startup and recovery flows are functional but not yet release-hardened.
  - Packaging, signing, installation, and benchmark gating are not yet first-class repository workflows.

## Assumptions

- Earlier phases have already stabilized the runtime, routing, and endpoint set that the desktop product will expose.
- The native macOS shell remains the primary operator surface.
- Packaging and release assets belong in versioned repository paths, not in undocumented manual setup.
- Release hardening requires benchmarks and smoke evidence, not only functional test pass/fail status.

## Performance Probes and Metrics

Required probes:

- `desktop.cold_boot_to_ready_ms`
- `desktop.operator_action_latency_ms`
- `desktop.restart_recovery_ms`
- `desktop.crash_recovery_success_rate`
- `release.benchmark_regression_pct`
- `release.smoke_pass_rate`
- `install.success_rate`

Required comparison report:

- cold boot and restart performance before vs after productization changes
- benchmark baselines for the supported model families
- release candidate smoke and recovery results against the previous stable baseline

## Work Plan

### Task 1: Upgrade the native operator shell from placeholder workflows to product-grade operations

**Objective**

Evolve the macOS app into a coherent operator-facing product surface backed entirely by the control plane.

**Files**

- Modify: `apps/macos-menubar/Sources/**/*`
- Modify tests under `apps/macos-menubar/Tests`
- Modify related control-plane XPC surfaces only where required for the new operator workflows

**Implementation**

- Add dashboard, model status, request health, logs, diagnostics, and preset-aware controls only where backend support already exists.
- Keep the app as an operator and product shell, not a second control plane.
- Ensure the app hydrates from control-plane state rather than worker-private state.

**Verification**

- `swift test --package-path apps/macos-menubar`

**Acceptance**

- The native shell surfaces the product state needed for daily local operation and diagnosis.

### Task 2: Add diagnostics, doctor, bench, and recovery workflows

**Objective**

Make local diagnosis and recovery reproducible instead of ad hoc.

**Files**

- Create or modify: `scripts/*`
- Create or modify: `docs/runbooks/*`
- Modify relevant control-plane or app code only where workflow support is required

**Implementation**

- Add doctor, bench, and recovery entrypoints for supported runtime families.
- Document startup, shutdown, restart, crash recovery, and common failure diagnosis.
- Ensure each operator workflow has explicit evidence outputs rather than hidden side effects.

**Verification**

- `make integration-test`
- workflow-specific smoke commands defined during implementation

**Acceptance**

- Operators can reproduce diagnosis and recovery workflows from repository artifacts alone.

### Task 3: Add packaging, signing, startup automation, and install assets

**Objective**

Turn local development assets into repeatable product packaging and launch workflows.

**Files**

- Create or modify: packaging and automation assets under the canonical repository location chosen during implementation
- Modify: `README.md`
- Create or modify: `docs/runbooks/*`

**Implementation**

- Add launchd or equivalent startup automation for the supported desktop product flow.
- Add packaging, signing, installation, and upgrade instructions and assets.
- Keep install and upgrade steps reproducible and versioned.

**Verification**

- packaging and install smoke commands defined during implementation

**Acceptance**

- Fresh install to ready-state is reproducible from repository workflows and docs.

### Task 4: Formalize release gates around smoke, benchmark, and recovery evidence

**Objective**

Make release readiness evidence-based rather than subjective.

**Files**

- Create or modify: benchmark scripts and smoke scripts under `scripts/`
- Create or modify: `docs/runbooks/*`
- Modify CI or release workflow assets in the repository where applicable

**Implementation**

- Define benchmark thresholds, smoke expectations, and restart or recovery gates.
- Store release evidence in reproducible report formats.
- Ensure regressions are detected before merge or release tagging, not after distribution.

**Verification**

- benchmark and smoke commands defined during implementation

**Acceptance**

- Release candidates carry benchmark, smoke, and recovery evidence rather than only test pass/fail logs.

### Task 5: Add final integration evidence and product-level metrics reporting

**Objective**

Leave Phase 8 with a release-grade evidence trail for the desktop product and operator workflows.

**Files**

- Modify: `tests/integration/*`
- Create or modify: `docs/runbooks/*`
- Modify: `README.md`

**Implementation**

- Add product-level integration scenarios for install, boot, restart, operator actions, and recovery.
- Standardize the Phase 8 metrics report for cold boot, operator latency, recovery, install success, and benchmark regressions.
- Ensure doc updates make the product workflow discoverable from the repository entrypoints.

**Verification**

- `make swift-test`
- `make py-test`
- `make integration-test`
- `make coverage`
- benchmark and smoke commands defined during implementation

**Acceptance**

- Product-level evidence is reproducible and discoverable.
- The touched scope meets the `>=95%` coverage rule where measurable.
- The Phase 8 metrics report contains non-`N/A` product and release numbers.

## Verification

```bash
make swift-test
make py-test
make integration-test
make coverage
```

Expected evidence:

- the macOS operator shell passes its own tests
- integration covers product boot, restart, and recovery workflows
- packaging and install smoke commands are documented and reproducible
- touched-scope coverage is at least `95%` where measurable
- the metrics report includes cold boot, operator latency, recovery, and benchmark data

## Acceptance Criteria

- Melix has a native desktop operator surface that reflects product-grade workflows rather than only engineering scaffolding.
- Startup, shutdown, restart, and recovery are reproducible from repository workflows and runbooks.
- Packaging, signing, installation, and upgrade steps are versioned and documented.
- Release candidates are gated by benchmark, smoke, and recovery evidence.
- Phase 8 concludes with reproducible productization and release-hardening metrics.

## Rollback or Safe Exit

- Land UI, diagnostics, packaging, and release-gate work in separate slices so runtime functionality remains independently verifiable.
- Keep new product workflows behind documented smoke checks until each path is stable.
- If a packaging or release automation slice is not yet robust, stop at the last reproducible operator workflow rather than shipping undocumented manual release steps.
