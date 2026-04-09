# Phase 8 CLI-First Acceptance Closure Design

## Summary

Melix should close the remaining Phase 8 product-acceptance gaps by making the public `melix` CLI
the authoritative contract for the remaining model-management, training, benchmark, evaluation, and
acceptance-evidence workflows, then wrapping the native Window UI around those same CLI behaviors.

The approved direction is:

- implement the remaining product gaps in the CLI first
- keep Window UI as a product shell that invokes CLI-first workflows rather than inventing a second
  orchestration path
- close the two open model-management gaps:
  - rebind the primary text-serving session to a newly downloaded Hugging Face text model without
    relying on `MELIX_DEV_TEXT_MODEL_PATH`
  - add a first-class local import workflow that materializes operator-selected local models into
    managed storage instead of depending only on registry-root scanning
- require positive and negative unit coverage plus deterministic end-to-end coverage for every new
  or materially changed Phase 8 workflow
- produce real acceptance evidence for CLI and Window UI flows with the live text model
  `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`
- deliver the work in staged slices, squashing each completed stage into local `main` before
  starting the next stage from the refreshed local `main`

## Problem

`docs/runbooks/phase-8-product-acceptance.md` still leaves two classes of work open:

1. implemented flows that need fresh live acceptance evidence before release sign-off
2. open product gaps that are not yet closed behavior

The current repository state has four concrete closure problems:

1. A downloaded Hugging Face text model can be materialized into managed storage, but the remaining
   operator workflow is not yet closed around primary-session rebinding and acceptance evidence.
2. Local-model onboarding still depends on registry-root scanning instead of a first-class
   materialize-into-managed-storage workflow.
3. The Window UI still owns product workflow behavior directly for many operations instead of
   treating the CLI as the first product contract.
4. The repository lacks one unified acceptance evidence bundle that records the exact model ID,
   dataset ID, suite IDs, job IDs, export paths, metrics, and screenshots required to close the
   remaining acceptance buckets.

Without a CLI-first closure, Melix risks shipping the same behavior through multiple partially
aligned entry points and makes Phase 8 acceptance evidence harder to reproduce.

## Constraints

- Use `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` as the live text model for real acceptance.
- Keep formal repository documentation in English.
- Treat the existing `melix` CLI command family as the primary operator contract for new behavior.
- Keep the Swift control plane as orchestration truth and the Python worker as execution truth.
- Do not rely on `MELIX_DEV_TEXT_MODEL_PATH` for the acceptance path being closed in this slice.
- Deliver in stages, with each completed stage squashed into local `main` before the next stage
  begins.
- Every new or changed feature must have:
  - positive unit tests
  - negative unit tests
  - deterministic end-to-end coverage
  - live acceptance evidence where the runbook requires real-runtime proof

## Approaches

### 1. Finish the Window UI directly and retrofit the CLI later

- Continue extending app-owned view-model logic first.
- Backfill CLI parity after the product flow works in the desktop shell.

Pros:

- Lowest short-term friction for the existing app code.

Cons:

- Violates the approved CLI-first delivery order.
- Creates a high risk of CLI or UI semantic drift.
- Makes deterministic testing and live evidence harder to standardize.

Rejected.

### 2. Move the entire desktop shell to pure CLI subprocess orchestration immediately

- Treat every read and write path in the Window UI as a shell-out to `melix`.
- Remove direct app-to-control-plane behavior as part of this closure.

Pros:

- Maximal CLI purity.
- One obvious product contract for every app surface.

Cons:

- Too broad for the remaining Phase 8 closure.
- Expands risk from product-gap closure into a full desktop architecture rewrite.
- Likely destabilizes unrelated app surfaces.

Rejected.

### 3. CLI-first product workflows with a hybrid Window UI CLI bridge

- Add or finish the missing product workflows in `melix`.
- Keep existing read-oriented desktop plumbing where it is already stable.
- Route the remaining productized workflow actions through a CLI invocation layer.
- Use a subprocess-backed invoker in production and a runner-backed seam in tests.

Pros:

- Matches the approved CLI-first requirement.
- Keeps the write-path semantics unified across CLI and Window UI.
- Preserves a tractable scope for the remaining Phase 8 closure.
- Makes deterministic testing and live evidence much easier to standardize.

Cons:

- Requires a careful boundary so Window UI does not half-own the same workflows.
- Adds subprocess lifecycle concerns for the app shell.

Recommended.

## Recommended Design

### CLI As The Product Contract

The public `melix` CLI becomes the authoritative product contract for the remaining acceptance
closure flows. The goal is not to rewrite every existing app capability, but to ensure that every
remaining Phase 8 product workflow is first implemented and verified through CLI semantics.

The CLI should own at least these operator-visible workflows:

- managed Hugging Face model download
- first-class local model import into managed storage
- registry refresh and catalog visibility checks
- server-session rebinding to a chosen managed model
- server-session start and readiness verification
- base-model chat acceptance request
- LoRA train, activate, list, and derived-model targeting
- benchmark, matrix benchmark, evaluation, and export operations
- acceptance evidence bundle creation and persistence

The existing command families should remain the base structure. This slice should prefer adding the
smallest possible CLI extension over inventing an unrelated command tree.

The expected additions are:

- one first-class local-import command under `melix model`
- structured result output from managed download or import commands that includes the managed model
  identity needed by later steps
- one repository-owned acceptance runner entrypoint that shells out to `melix` commands in a
  reproducible order and writes a machine-readable evidence bundle

### Managed Model Materialization

Both Hugging Face downloads and local imports should converge on one productized materialization
shape:

- artifact bytes or directories land under the managed model root
- Melix writes or normalizes a managed manifest with a stable model identity
- the resulting model is visible through the registry snapshot and model catalog without depending
  on ad hoc environment fallback

For the local-import gap, v1 should explicitly materialize the selected model into managed storage.
This slice should not attempt a zero-copy aliasing scheme or a background sync daemon. A clear,
predictable materialized copy is the right acceptance target.

Both managed download and local import should return a typed result that includes:

- `model_id`
- `managed_model_path`
- `source_kind`
- `source_locator`
- any operator-facing warnings that still permit success

This gives the next CLI step enough information to rebind a server session without asking the user
to rediscover the imported model through a separate manual lookup.

### Server-Session Rebinding Closure

The remaining rebinding gap should be closed by composing the existing session-management surfaces
around the newly materialized model identity.

The intended Phase 8 acceptance path is:

1. materialize a Hugging Face or local text model into managed storage
2. refresh the registry snapshot
3. update the target server session to the returned managed `model_id`
4. select that session as the active primary session
5. start the server session
6. verify chat traffic against that bound managed model

This flow must not require `MELIX_DEV_TEXT_MODEL_PATH`.

No second rebinding source of truth should be introduced in the Window UI. The CLI should own the
binding semantics, while the control plane continues to own validation for:

- model existence
- serveable model kind
- unavailable-binding preservation
- start-time readiness validation

### Window UI As A CLI Shell

The Window UI should become a product shell around CLI-first workflows rather than re-implementing
their write-path orchestration.

This slice should use a hybrid bridge:

- production:
  - the app invokes the bundled `melix` executable as a subprocess
  - JSON output mode is required for structured workflow actions
- tests:
  - the app injects a protocol-backed CLI invoker that exercises the same command semantics without
    launching a real subprocess

The app should remain free to use stable read-oriented view state that already exists today. The
scope boundary is narrower:

- any newly closed Phase 8 workflow action should route through CLI-first semantics
- the app should present command progress, typed success state, typed failure state, and artifact or
  evidence paths without owning a second workflow engine

This keeps the Window UI aligned with the CLI without forcing a full app architecture rewrite in
the same transaction.

### Acceptance Evidence Bundle

Melix should persist one reproducible evidence bundle per live acceptance run under a product-owned
path such as:

- `MELIX_HOME/acceptance/phase8/<timestamp>-<model-slug>/`

The bundle should include:

- `manifest.json`
  - exact base model ID
  - exact derived model ID if one is activated
  - exact dataset ID used for LoRA training
  - exact benchmark suites
  - exact matrix benchmark suites
  - exact evaluation suite and dataset ID
  - server session ID
  - job IDs
  - export paths
  - success or failure state per step
- `cli/`
  - structured command outputs or summarized transcripts
- `window-ui/`
  - workflow summaries and screenshot references
- `screenshots/`
  - captured Window UI evidence
- `exports/`
  - benchmark CSV exports
  - matrix CSV exports
  - evaluation CSV and JSONL exports
- `metrics/`
  - Phase 8 metrics JSON
  - Phase 8 release-gate JSON

The runbook should close the remaining Bucket 2 items by pointing to this evidence bundle rather
than relying on manually assembled notes.

### Acceptance Defaults

To keep live acceptance narrow and reproducible, this design fixes the primary Phase 8 acceptance
targets:

- live text model:
  - `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`
- live LoRA dataset:
  - add and use one checked-in tiny training dataset package at
    `services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1/`
- standard benchmark suites:
  - `smoke`
  - `latency`
- matrix benchmark suites:
  - `smoke`
- evaluation suite:
  - `mmlu`
- evaluation dataset:
  - `mmlu.dev.v1`

The acceptance bundle must record the exact chosen values even when they match these defaults.

### Testing Strategy

The testing contract for this closure has three layers.

#### 1. Positive And Negative Unit Tests

Every new or materially changed workflow needs both success and failure coverage.

Required CLI unit coverage includes:

- local-import command parsing and validation
- managed-import and download result decoding
- server-session rebinding and lifecycle chaining
- acceptance evidence manifest writing
- typed error reporting for invalid source paths, malformed local models, missing sessions,
  unserveable models, missing artifacts, invalid dataset parameters, and missing export targets

Required Window UI unit coverage includes:

- CLI command construction
- progress rendering from structured CLI updates
- typed error mapping from CLI failures into operator-facing UI state
- artifact and evidence-path presentation

#### 2. Deterministic End-To-End Coverage

Every productized workflow also needs deterministic end-to-end coverage that does not depend on a
real network download or long live training run.

Required deterministic CLI end-to-end flows:

- managed local import -> registry refresh -> session rebind -> start
- managed download result replay -> session rebind -> start
- base chat request
- LoRA train -> activate -> derived chat
- benchmark -> matrix -> evaluation -> export
- evidence bundle write

Required deterministic Window UI end-to-end flows:

- UI action dispatch into the CLI invoker seam
- progress, success, and failure rendering
- evidence screenshot or artifact registration

#### 3. Live Acceptance

The real Phase 8 closure still requires one live end-to-end acceptance run.

That live run must include:

- real managed download of `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`
- registry refresh and session rebinding without `MELIX_DEV_TEXT_MODEL_PATH`
- one base-model chat run
- one LoRA train and activate workflow
- one derived-model chat run
- one standard benchmark run
- one matrix benchmark run
- one evaluation run
- all required exports
- one CLI acceptance evidence bundle
- one Window UI acceptance evidence bundle with screenshots

### Performance Probes And Success Metrics

The existing Phase 8 metrics remain the primary product-readiness probes. This closure also needs a
small acceptance-orchestration probe set:

- `acceptance.cli.command_duration_ms`
- `acceptance.ui.cli_roundtrip_ms`
- `acceptance.bundle_write_ms`
- `acceptance.base_chat_duration_ms`
- `acceptance.derived_chat_duration_ms`

Success metrics for this design are:

- the two open Bucket 3 product gaps are closed
- the Bucket 2 live-validation items are backed by a reproducible evidence bundle
- the closed acceptance path does not require `MELIX_DEV_TEXT_MODEL_PATH`
- CLI and Window UI use the same workflow truth for the newly closed Phase 8 actions
- every changed feature ships with positive and negative unit coverage plus deterministic end-to-end
  coverage
- the live acceptance bundle records exact model, dataset, suite, export, and screenshot evidence

## Delivery Stages And Git Flow

This work should be delivered as staged slices rather than one long-running integration branch.

The approved stage order is:

1. CLI managed materialization
   - first-class local import
   - managed result contract normalization
2. CLI session rebinding and base chat closure
   - registry refresh
   - session update or select
   - server start
   - base chat acceptance
3. CLI LoRA, benchmark, evaluation, export, and evidence closure
   - derived-model chat
   - acceptance bundle generation
4. Window UI shell over CLI
   - subprocess invoker in production
   - injected runner seam in tests
5. Window UI live acceptance and runbook closure
   - screenshots
   - acceptance bundle references
   - Bucket status updates

For each stage:

1. branch from the latest local `main`
2. implement the stage with TDD and focused verification
3. run the required broader repository verification gates
4. squash-merge the stage back into local `main`
5. refresh local `main`
6. start the next stage from that refreshed local `main`

This workflow is part of the approved design, not an optional release preference.

## Scope Guardrails

- No full desktop architecture rewrite outside the CLI invocation boundary required for this slice.
- No new cloud training or remote orchestration service.
- No QLoRA expansion in this closure.
- No free-form arbitrary benchmark suite ingestion beyond the repository-owned suite model already
  used by Melix.
- No acceptance shortcut that omits either deterministic end-to-end coverage or live evidence.
- No reliance on unmanaged registry-root scanning as the only local-import product path.
