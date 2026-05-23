# M-Courtyard-Informed Melix Improvement Roadmap

## Title

M-Courtyard-informed Melix improvement roadmap

## Goal

Turn the M-Courtyard reference scan into a concrete Melix improvement backlog
that improves the project-centered LoRA, dataset, export, environment, and
storage workflows without weakening Melix's control-plane authority or evidence
contracts.

## Non-Goals

- Do not copy implementation code, UI assets, branding, or licensed material
  from the reference project.
- Do not replace Melix's current Phase 0-8 completion summary.
- Do not create a second source of truth outside the Swift control plane and
  schema-backed artifacts.
- Do not implement the listed features in this documentation pull request.

## Context

Relevant specs and scans:

- [`docs/reference-scans/m-courtyard-lessons.md`](../reference-scans/m-courtyard-lessons.md)
- [`docs/current-status.md`](../current-status.md)
- [`docs/architecture-spec.md`](../architecture-spec.md)
- [`docs/benchmark-evaluation-contract.md`](../benchmark-evaluation-contract.md)
- [`docs/agentic-trajectory-dataset-contract.md`](../agentic-trajectory-dataset-contract.md)
- [`docs/unified-agentic-tool-runtime-contract.md`](../unified-agentic-tool-runtime-contract.md)
- [`docs/evidence-telemetry-report-contract.md`](../evidence-telemetry-report-contract.md)
- [`docs/reference-scans/sparrow-localai-lessons.md`](../reference-scans/sparrow-localai-lessons.md)

Current constraints:

- Melix already ships local model management, server sessions, chat, LoRA and
  QLoRA, benchmark and evaluation, native macOS operator workflows, packaging,
  and release gates.
- The follow-up work must deepen the current product paths instead of reopening
  closed phase-roadmap scope.
- Formal implementation work must update the relevant governing spec, runbook,
  or plan and include performance probes and metrics for the changed path.

## Assumptions

- GitHub Issues are the tracker for milestone, plan, and executable-unit work.
- Issue titles use the `M-Courtyard roadmap` prefix so the backlog remains
  searchable without adding a new label.
- Parent-child relationships are recorded in issue bodies and this document,
  not through GitHub Milestones.
- `enhancement`, `documentation`, `operator-ux`, `runtime-health`,
  `bench-eval`, `run-evidence`, and `performance` are sufficient existing
  labels for the initial issue set.

## Issue Hierarchy

Issue numbers were filled after the GitHub issues were created.

| ID | Issue | Type | Blocked By |
|---|---|---|---|
| M1 | [#1490](https://github.com/Keith-CY/melix/issues/1490) | Milestone | None |
| P1.1 | [#1491](https://github.com/Keith-CY/melix/issues/1491) | Plan | M1 |
| U1.1.1 | [#1492](https://github.com/Keith-CY/melix/issues/1492) | Unit | P1.1 |
| U1.1.2 | [#1493](https://github.com/Keith-CY/melix/issues/1493) | Unit | P1.1 |
| P1.2 | [#1494](https://github.com/Keith-CY/melix/issues/1494) | Plan | M1 |
| U1.2.1 | [#1495](https://github.com/Keith-CY/melix/issues/1495) | Unit | P1.2 |
| U1.2.2 | [#1496](https://github.com/Keith-CY/melix/issues/1496) | Unit | P1.2 |
| M2 | [#1497](https://github.com/Keith-CY/melix/issues/1497) | Milestone | None |
| P2.1 | [#1498](https://github.com/Keith-CY/melix/issues/1498) | Plan | M2 |
| U2.1.1 | [#1499](https://github.com/Keith-CY/melix/issues/1499) | Unit | P2.1 |
| U2.1.2 | [#1500](https://github.com/Keith-CY/melix/issues/1500) | Unit | P2.1 |
| P2.2 | [#1501](https://github.com/Keith-CY/melix/issues/1501) | Plan | M2 |
| U2.2.1 | [#1502](https://github.com/Keith-CY/melix/issues/1502) | Unit | P2.2 |
| U2.2.2 | [#1503](https://github.com/Keith-CY/melix/issues/1503) | Unit | P2.2 |
| M3 | [#1504](https://github.com/Keith-CY/melix/issues/1504) | Milestone | None |
| P3.1 | [#1505](https://github.com/Keith-CY/melix/issues/1505) | Plan | M3 |
| U3.1.1 | [#1506](https://github.com/Keith-CY/melix/issues/1506) | Unit | P3.1 |
| U3.1.2 | [#1507](https://github.com/Keith-CY/melix/issues/1507) | Unit | P3.1 |
| P3.2 | [#1508](https://github.com/Keith-CY/melix/issues/1508) | Plan | M3 |
| U3.2.1 | [#1509](https://github.com/Keith-CY/melix/issues/1509) | Unit | P3.2 |
| U3.2.2 | [#1510](https://github.com/Keith-CY/melix/issues/1510) | Unit | P3.2 |
| M4 | [#1511](https://github.com/Keith-CY/melix/issues/1511) | Milestone | None |
| P4.1 | [#1512](https://github.com/Keith-CY/melix/issues/1512) | Plan | M4 |
| U4.1.1 | [#1513](https://github.com/Keith-CY/melix/issues/1513) | Unit | P4.1 |
| U4.1.2 | [#1514](https://github.com/Keith-CY/melix/issues/1514) | Unit | P4.1 |
| P4.2 | [#1515](https://github.com/Keith-CY/melix/issues/1515) | Plan | M4 |
| U4.2.1 | [#1516](https://github.com/Keith-CY/melix/issues/1516) | Unit | P4.2 |
| U4.2.2 | [#1517](https://github.com/Keith-CY/melix/issues/1517) | Unit | P4.2 |

## Work Plan

### Milestone M1: Guided Project Workspace and Dataset Preparation

**Outcome:** A Melix training project has a stable workspace identity,
manifest, dataset preparation path, versioned dataset outputs, and quality
evidence that can feed training, evaluation, export, and reports.

**Reference advantages:** guided end-to-end path, project artifact layout,
document ingest quality controls, dataset versions, failed retry, quality
summary, and mode recommendation.

**Measurement direction:** workspace validation latency, document ingest
throughput, segmentation counts, PII mask count, dedup ratio, dataset listing
latency, failed retry success rate, and quality scoring latency.

#### Plan P1.1: Project Workspace Contract and Artifact Inventory

Define the workspace contract that joins raw inputs, cleaned data, generated
datasets, adapters, logs, exports, reports, and evidence bundles under one
Melix-owned project identity.

##### Unit U1.1.1: Define Workspace Manifest and Artifact Paths

Build the schema and docs for a `workspace-manifest.json` that records project
identity, artifact roots, artifact types, provenance references, schema
version, and redaction policy. The unit is complete when a fixture manifest can
be validated and linked from current LoRA and evaluation docs.

##### Unit U1.1.2: Add Workspace Preflight and Migration Validation

Add CLI and operator preflight behavior that detects missing roots, stale
schema versions, unmanaged artifacts, and unsafe paths before dataset
preparation or training starts. The unit is complete when preflight writes a
machine-readable receipt and the UI can explain each failure.

#### Plan P1.2: Dataset Preparation Quality and Versioning

Productize dataset preparation as a reusable Melix path with explicit quality
controls, version metadata, retry behavior, and reportable metrics.

##### Unit U1.2.1: Add Document Ingest Cleaning Quality Controls

Add text, PDF, DOCX, markdown, code, and structured-data ingest with PII
masking, exact deduplication, fuzzy deduplication, and strategy-specific
segmentation receipts. The unit is complete when sample fixtures produce
stable segment counts and quality-control metrics.

##### Unit U1.2.2: Add Dataset Versions, Failed-Segment Retry, and Quality Summary

Create versioned dataset directories with metadata, train/validation counts,
failed-segment files, failed-only retry, and a quality summary that can be
rendered in CLI, Desktop, and reports. The unit is complete when a failed
generation can be repaired without rewriting the successful samples.

### Milestone M2: Training Monitor and Adapter Provenance

**Outcome:** Training jobs have stronger preflight validation, durable local
admission, structured run state, smart alerts, and adapter provenance that
survives export, comparison, and publish workflows.

**Reference advantages:** trainability guardrails, complete training metadata,
live training events and smart alerts, and a local training queue.

**Measurement direction:** trainability preflight latency, queue admission
latency, queue restore latency, log parser throughput, alert detection latency,
adapter manifest write latency, and loss-series row count.

#### Plan P2.1: Training Parameter Safety and Queueing

Add explicit trainability checks and a durable admission path for local
training so unsupported runs fail early and queued runs survive navigation or
process restart.

##### Unit U2.1.1: Add Trainability Guardrails for Unsupported Configurations

Validate model family, quantization, fine-tune type, LoRA target coverage,
sequence length, sample count, and memory fit before training starts. The unit
is complete when known unsupported combinations return typed operator errors
with no worker launch.

##### Unit U2.1.2: Add Durable Local Training Queue Admission and Status

Persist queued and running training jobs with project identity, model,
dataset version, resource class, cancellation state, and recovery policy. The
unit is complete when a queued run can be restored after app restart and no two
exclusive local training jobs can run concurrently.

#### Plan P2.2: Training Monitor and Adapter History

Turn training output into structured product state and connect completed
adapters to provenance, notes, charts, and comparison inputs.

##### Unit U2.2.1: Parse Training Logs Into Structured Run Events

Parse loss, validation loss, ETA, step count, OOM, Metal watchdog, stalled
progress, rising loss, and final summary events into a typed stream. The unit
is complete when fixtures produce deterministic alert rows and reportable
diagnostic counters.

##### Unit U2.2.2: Persist Adapter Provenance, Loss Series, and Notes

Create an adapter provenance manifest that records base model, dataset version,
hyperparameters, train/validation sample counts, loss series, final metrics,
operator notes, and export eligibility. The unit is complete when adapter
history and comparison views read from the manifest rather than ad hoc logs.

### Milestone M3: Runtime-Aware Export and Serving Verification

**Outcome:** Exported adapters and fused models have target-specific manifests,
retention policy, smoke tests, diagnostics, and a short path to being served
locally through Melix or compatible runtimes.

**Reference advantages:** multi-target export, post-export smoke test, export
failure diagnosis, and serving exported artifacts.

**Measurement direction:** export planning latency, artifact size, export
duration, load smoke latency, generation smoke latency, diagnostic parser
coverage, and retained artifact size.

#### Plan P3.1: Multi-Target Export Contract

Define and implement a target-aware export contract for Melix managed
artifacts, Ollama, GGUF, and MLX-compatible local runtimes.

##### Unit U3.1.1: Define Export Target Manifest for Melix, Ollama, GGUF, and MLX

Define the schema, runbook, and fixtures for export target manifests that
record target type, source adapter, base model, quantization, generated files,
runtime requirements, and verification policy. The unit is complete when all
export targets can be represented without target-specific side channels.

##### Unit U3.1.2: Implement Export Artifact Layout and Retention Policy

Implement a predictable export directory layout and retention policy for fused
models, intermediate files, manifests, runtime logs, and smoke-test evidence.
The unit is complete when cleanup can distinguish required artifacts from
safe-to-delete intermediates.

#### Plan P3.2: Post-Export Smoke and Diagnostics

Require export completion to prove the artifact can be inspected, loaded, and
used for at least one bounded generation path, then surface actionable
diagnostics when it cannot.

##### Unit U3.2.1: Add Post-Export Load and Generation Smoke Test

Add bounded metadata and generation checks for each export target and record
latency, output preview, failure mode, and evidence path. The unit is complete
when an export cannot be marked successful until its target smoke policy
passes or is explicitly waived with a recorded reason.

##### Unit U3.2.2: Add Export Failure Diagnostics From Runtime Logs

Parse target runtime logs for common load failures, unsupported architecture
errors, duplicate tensor names, missing blobs, missing binaries, invalid
runtime paths, and timeout cases. The unit is complete when the CLI and
Desktop show typed remedies and redacted evidence.

### Milestone M4: Local Runtime Integration, Environment, and Storage Operations

**Outcome:** Melix can inspect external local model inventories, diagnose the
Desktop execution environment, and manage large workspace artifacts safely.

**Reference advantages:** app-managed environment setup, GUI PATH recovery,
proxy and certificate support, cross-runtime model discovery, and safe storage
cleanup.

**Measurement direction:** inventory scan latency, scan payload size,
diagnostic latency, redaction coverage, storage inventory latency, cleanup
dry-run latency, and safe-delete count.

#### Plan P4.1: Cross-Runtime Model Inventory

Extend model discovery with explicit source descriptors for Melix-managed
models and compatible local runtime caches.

##### Unit U4.1.1: Add External Runtime Source Descriptors

Define source descriptors for Hugging Face cache snapshots, ModelScope cache
snapshots, Ollama model stores, LM Studio model stores, and Melix-managed
roots. The unit is complete when each source has an explicit path policy,
discovery receipt, and redaction rule.

##### Unit U4.1.2: Add Scan Receipts and Usability Classification

Classify discovered models by source, file layout, family signal, MLX
compatibility, trainability, exportability, missing-file state, and estimated
size. The unit is complete when CLI, Desktop, and diagnostics share one
machine-readable scan receipt.

#### Plan P4.2: Desktop Environment Doctor and Storage Cleanup

Add operator-facing diagnostics and safe cleanup for the local environment,
workspace roots, checkpoints, exports, and runtime caches.

##### Unit U4.2.1: Add GUI Shell PATH, Proxy, Certificate, and Runtime Diagnostics

Diagnose packaged-app PATH, uv/Python/MLX versions, runtime binary paths,
proxy variables, certificate variables, and local server health. The unit is
complete when diagnostics can explain Finder-launched app failures without
printing secrets.

##### Unit U4.2.2: Add Storage Inventory and Safe Cleanup Plan

Inventory workspace raw files, cleaned segments, dataset versions, checkpoints,
adapter outputs, export intermediates, runtime logs, and stale temp files.
The unit is complete when dry-run and apply modes protect active jobs and
write a cleanup receipt.

## Verification

This roadmap is documentation-only. The pull request that introduces it should
run:

```bash
git diff --check
python3 scripts/validate_pr_evidence.py --body-file .runtime/pr-body-m-courtyard-roadmap.md
```

The changed scope has no executable code and no measurable runtime coverage.
Metrics report: `N/A - documentation-only roadmap; follow-up implementation
issues define their own probes and metrics.`

## Acceptance Criteria

- The reference scan lists concrete advantages from the reference project and
  maps each advantage to a Melix improvement direction.
- This roadmap groups those improvements into milestones, plans, and executable
  units.
- GitHub issues exist for every milestone, plan, and executable unit.
- The roadmap links each issue after creation.
- Each issue includes acceptance criteria, blocker relationships, governing
  docs, and metrics expectations.
- Each issue is delegated to an agent for implementation readiness.
- The documentation pull request links this roadmap and records docs-only
  verification plus metrics `N/A`.

## Rollback or Safe Exit

- If issue creation fails partway through, leave already-created issues open,
  record the last created issue in this document, and resume creation from the
  next missing ID.
- If the roadmap needs to be withdrawn, close the generated issues with a link
  to the replacing plan and revert the documentation commit.
