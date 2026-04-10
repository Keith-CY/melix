# Benchmark, Matrix, And Evaluation Closure Design

## Context

Melix already ships product-facing `bench`, `bench matrix`, and `eval` workflows across the public
`melix` CLI, the Swift control plane, the Python model-operations worker, persisted artifact roots,
and the Window UI. The repository also carries several follow-on designs that extend those
workflows into multimodal evaluation, LoRA comparison, executable code evaluation, statistical
reporting, and release-gate integration.

The current problem is no longer schema absence or UI absence in isolation. The problem is closure:

- some benchmark and evaluation paths still rely on deterministic evidence where live MLX runtime
  evidence is required
- some designed capabilities exist only as plans or partial worker foundations
- acceptance expectations differ across CLI, Window UI, worker execution, and release evidence
- the current Window UI owns too much product behavior directly instead of acting as a thin shell
  over one CLI-owned workflow layer

This design defines the closure program for the remaining benchmark, matrix, and evaluation scope.
It does not execute that program directly. It defines the phased architecture, product boundaries,
acceptance model, and git workflow required before implementation begins.

## Goal

Close the existing and already-designed benchmark, matrix, and evaluation capability set into a
phased CLI-first product program where each phase reaches explicit CLI acceptance, Window UI
acceptance, positive and negative unit coverage, positive and negative end-to-end coverage, and a
clean squash-merge handoff into local `main` before the next phase starts.

## Non-Goals

This design does not cover:

- implementation work in this transaction
- audio or video evaluation expansion
- cloud-hosted benchmark or evaluation infrastructure
- replacing existing repository-owned artifact schemas unless a later phase explicitly updates the
  canonical contract
- forcing one text-only acceptance model to stand in for multimodal image-grounded evaluation

## Decision Summary

### 1. Program Structure

Use one master specification plus one master orchestration plan.

The master specification defines:

- scope
- phase boundaries
- architectural constraints
- acceptance rules
- git workflow

The master plan sequences the implementation program into independently acceptable phases and
points each phase at the canonical docs, code paths, verification commands, and merge gates.

The master plan is orchestration-level only. Before any phase starts code changes, that phase must
also have a phase-specific execution plan that names the exact files, test slices, acceptance
workflows, and metrics capture steps for the phase.

### 2. CLI-First Product Behavior

`MelixCLICore` is the single product-behavior source of truth for benchmark, matrix, and evaluation
workflows.

CLI-owned responsibilities include:

- command vocabulary
- parameter normalization
- defaulting rules
- validation behavior
- export semantics
- error mapping
- acceptance wording

Window UI must not maintain a second behavior layer for those responsibilities.

### 3. Window UI Mixed Execution Model

Window UI will use a mixed integration model:

- production mode: invoke the public `melix` executable as a subprocess
- test mode: invoke the same CLI workflow through a shared CLI runner seam

This is the required compromise between product truth and testability.

Why this model:

- production behavior satisfies the product requirement that the UI truly drives `melix`
- test behavior keeps unit and end-to-end coverage deterministic, injectable, and fast
- both modes reuse one CLI-owned workflow layer instead of duplicating logic in SwiftUI

### 4. Phase Handoff Policy

Each implementation phase must end with:

1. phase-scoped CLI acceptance
2. phase-scoped Window UI acceptance
3. phase-scoped positive and negative UT completion
4. phase-scoped positive and negative E2E completion
5. squash merge into local `main`
6. local `main` refresh and intended-base sync before the next phase begins

No partially accepted phase is allowed to flow into the next phase.

## Acceptance Model Baselines

### Text Acceptance Model

The default small text model for benchmark, matrix, evaluation, CLI acceptance, UI acceptance, and
phase-scoped end-to-end coverage is:

- `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`

This model becomes the default text acceptance anchor across the closure program unless a later
approved contract update changes it.

### Multimodal Acceptance Model

Text-only acceptance does not replace image-grounded acceptance.

For multimodal evaluation and VLM benchmark phases, the default image-grounded acceptance anchor
remains the smallest documented repository-owned image-evaluation target already present in the
runbooks:

- `mlx-community/paligemma2-3b-ft-docci-448-8bit`

Phase-specific plans may add a second targeted VLM acceptance model when required by family-
specific behavior, but they must not remove the baseline image-grounded acceptance path without an
explicit contract update.

## Scope Model

The closure program includes all remaining work needed to bring the benchmark, matrix, and
evaluation stack to accepted product state across:

- CLI
- Window UI
- control-plane orchestration
- worker execution
- persisted artifacts
- exports
- release-style evidence

The included product lines are:

- standard `bench`
- `bench matrix`
- `eval`
- evaluation comparison workflows
- raw and structured export workflows
- executable code evaluation for code suites
- release-gate evidence derived from persisted benchmark and evaluation artifacts

The included UI obligations are:

- independent UI workflows for:
  - comparison
  - release gates
- integrated UI workflows inside existing `Diagnostics / Benchmark / Evaluation` surfaces for:
  - code-execution evaluation
  - VLM benchmark enrichments
  - raw export and artifact inspection

## Architecture

### Product Behavior Ownership

The stack is organized around one behavior chain:

1. canonical contract and runbook semantics
2. `MelixCLICore` normalization and workflow execution
3. Swift control-plane orchestration and target resolution
4. Python worker execution and artifact truth
5. persisted exports and acceptance evidence
6. Window UI as an operator shell over CLI workflows

This design intentionally rejects a second Window UI behavior model.

### CLI-Owned Workflow Layer

Every benchmark, matrix, evaluation, comparison, export, and release-gate workflow must expose a
CLI-owned shape first.

That CLI-owned shape must define:

- required inputs
- defaults
- negative validation behavior
- human-readable output
- `--json` output
- export artifact semantics
- machine-readable error surfaces

Only after the CLI shape is complete and accepted may the Window UI integrate it.

### Window UI Responsibilities

Window UI is responsible for:

- collecting user input
- mapping that input into a CLI workflow invocation
- displaying in-progress state
- presenting success results
- presenting failure results
- exposing artifact locations and export actions

Window UI is not responsible for:

- owning benchmark or evaluation normalization rules
- inventing alternate default values
- implementing export schemas
- shaping result semantics differently from CLI

### Test-Mode Seam

The test seam must expose the same workflow contracts used by production CLI invocations.

Required test seam characteristics:

- deterministic success injection
- deterministic failure injection
- argument capture
- artifact fixture injection
- output fixture injection

The seam must prove UI-to-CLI integration semantics without requiring a real subprocess for every
test.

### Production Subprocess Proof

The seam is not sufficient on its own.

Each phase that changes Window UI behavior must also include at least one production-mode
subprocess proof that demonstrates:

- the UI can launch the `melix` subprocess
- the subprocess invocation maps the intended CLI workflow
- the returned output is rendered correctly
- production-mode subprocess failures surface correctly in the UI

## Unified Acceptance Matrix

Every implementation phase must satisfy all of the following acceptance classes.

### CLI Positive Unit Tests

These prove:

- command parsing succeeds for valid phase inputs
- normalized requests preserve the canonical phase contract
- success rendering and export shaping remain stable

### CLI Negative Unit Tests

These prove:

- invalid combinations are rejected explicitly
- unsupported targets and task families fail with stable diagnostics
- malformed or missing export artifacts are surfaced predictably

### CLI Positive End-To-End Tests

These prove:

- the phase workflow succeeds against the designated acceptance model or fixture
- persisted artifacts are written correctly
- exported outputs match the phase contract

### CLI Negative End-To-End Tests

These prove:

- runtime failures are surfaced honestly
- unsupported datasets, incompatible targets, invalid policies, or missing artifacts fail closed
- release-style verdict paths do not silently degrade

### Window UI Positive Unit Tests

These prove:

- UI state maps correctly into the CLI seam
- successful CLI outputs rebuild the expected view state
- artifact and history presentation is derived from CLI-owned outputs

### Window UI Negative Unit Tests

These prove:

- CLI seam failures map to the intended local UI failure states
- invalid user input produces the intended guard rails before invocation
- subprocess launch failures and malformed outputs remain operator-visible

### Window UI Positive End-To-End Tests

These prove:

- the intended UI workflow can be completed end to end
- success output is visible in the intended surface
- exported artifacts and result summaries are operator-visible

### Window UI Negative End-To-End Tests

These prove:

- the intended UI workflow fails visibly and correctly when the CLI workflow or subprocess fails
- guarded invalid inputs remain blocked in the UI
- failure evidence remains accessible instead of being collapsed into generic local error text

### CLI Acceptance

CLI acceptance is a documented, reproducible operator workflow that uses the designated acceptance
model or fixture and produces the expected artifact and output set.

### Window UI Acceptance

Window UI acceptance is a documented, reproducible operator workflow that exercises the same phase
through the UI, including at least one visible failure path.

## Phase Program

### Phase 1: Baseline CLI-First Closure

Outcome:

- existing `bench`, `bench matrix`, and `eval` workflows become reliable, CLI-owned, and honestly
  backed by live MLX evidence where the product claims live execution

Scope:

- real MLX benchmark closure
- real MLX evaluation closure
- CLI-first workflow ownership for existing standard benchmark, matrix, evaluation, and export
- Window UI migration onto the mixed CLI integration model for existing benchmark and evaluation
  surfaces

Dependencies:

- none

Independent acceptance gate:

- no later phase can start until Phase 1 CLI and Window UI both pass their own positive and
  negative UT and E2E suites

### Phase 2: Multimodal Evaluation And VLM Benchmark Closure

Outcome:

- multimodal evaluation and VLM benchmark behavior become first-class product capabilities rather
  than partial foundations

Scope:

- image-grounded evaluation closure
- VLM benchmark parameter and output closure
- integrated Window UI support inside existing benchmark and evaluation surfaces

Dependencies:

- Phase 1

### Phase 3: Comparison And Raw Export Closure

Outcome:

- LoRA comparison and raw export become first-class operator workflows

Scope:

- comparison job family
- paired exports and regression summaries
- raw JSON export closure
- independent Window UI comparison workflow

Dependencies:

- Phase 1
- Phase 2 is recommended before broad multimodal comparison, but not required for text-only
  comparison closure

### Phase 4: Semantic Evaluation Controls And Executable Code Evaluation

Outcome:

- evaluation control knobs become semantically real and code-suite scoring becomes evidence-bearing

Scope:

- `few_shot`, `seed`, `scoring_mode`, and `code_exec_policy` semantics
- executable code evaluation for `humaneval` and `mbpp`
- integrated Window UI evidence and failure-state support inside the existing evaluation surface

Dependencies:

- Phase 1

### Phase 5: Statistical Reporting And Release-Gate Closure

Outcome:

- benchmark and evaluation evidence becomes strong enough for release-style decisions

Scope:

- confidence intervals or bootstrap reporting
- release-style evidence summaries
- benchmark and evaluation release-gate integration
- independent Window UI release-gate workflow

Dependencies:

- Phase 3
- Phase 4

## Cross-Phase Git Workflow

Each phase uses the same git discipline:

1. start from current local `main`
2. create the phase branch or detached-worktree head for that phase only
3. complete phase-scoped implementation and verification
4. complete phase-scoped CLI acceptance and Window UI acceptance
5. squash merge the phase into local `main`
6. refresh local `main` and sync it with the intended base before the next phase
7. create or rebase the next phase head onto that refreshed local `main`

The closure program must not accumulate multiple incomplete phases on one long-running branch.

## Required Evidence Per Phase

Every phase handoff must include:

- phase summary
- changed scope
- path to the phase-specific execution plan used for the phase
- designated acceptance model or fixture
- targeted verification command outcomes
- positive and negative UT evidence
- positive and negative E2E evidence
- CLI acceptance notes
- Window UI acceptance notes
- metrics report for the touched scope, or explicit `N/A` when the scope is documentation-only and
  no measurable executable path changed
- explicit statement that the phase was squash merged into local `main`

## Risks And Guard Rails

### 1. Behavior Drift Between CLI And UI

Guard rail:

- keep all product semantics CLI-owned
- prohibit duplicate UI defaults or parallel export shaping

### 2. False Evidence From Deterministic Or Synthetic Paths

Guard rail:

- any evidence-bearing runtime path must prove whether it is live MLX or deterministic
- negative tests must cover unsupported live-runtime combinations explicitly

### 3. Unstable UI Testing From Real Subprocess Usage

Guard rail:

- use the shared CLI runner seam for the majority of UI UT and E2E coverage
- add only the minimum production subprocess proofs required to validate product truth

### 4. Phase Bleed

Guard rail:

- no new phase starts before the previous phase has cleared its merge gate
- each phase must own its own acceptance doc updates, tests, and merge evidence

### 5. Multimodal Model Baseline Drift

Guard rail:

- keep the text acceptance baseline fixed to `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`
- keep at least one documented image-grounded VLM acceptance baseline for multimodal phases

## Acceptance

This closure design is accepted when:

- the repository has one approved master specification and one approved master orchestration plan
  for benchmark, matrix, and evaluation closure
- the specification fixes CLI-first ownership, mixed Window UI execution, phase boundaries,
  acceptance classes, and phase merge workflow
- the plan sequences the implementation program into independently acceptable phases without mixing
  incomplete phases on one branch
- the designated text acceptance model is explicitly recorded as
  `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`
