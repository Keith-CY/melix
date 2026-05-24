# M-Courtyard Reference Scan

## Purpose

This reference scan records product and architecture lessons from
M-Courtyard that are relevant to Melix. The scan compares the external project
with Melix's current local-first runtime scope, identifies advantages worth
borrowing, and defines the follow-up roadmap that turns those lessons into
Melix issues.

The scan is a planning artifact only. It does not import source code,
dependencies, assets, branding, or license obligations from the reference
project.

## Sources

The reference repository was inspected at commit
`d560d1b1337a9c5f45724fb36b12e12d35c49372`.

| Source | Reference Scope |
|---|---|
| [M-Courtyard README](https://github.com/Mcourtyard/m-courtyard/blob/d560d1b1337a9c5f45724fb36b12e12d35c49372/README.md) | Product positioning, four-step local fine-tuning workflow, data preparation, training, testing, export, and runtime support |
| [`app/src/`](https://github.com/Mcourtyard/m-courtyard/tree/d560d1b1337a9c5f45724fb36b12e12d35c49372/app/src) | React desktop workflow pages, Zustand stores, notification state, model selector, training queue, and testing/export surfaces |
| [`app/src-tauri/src/commands/`](https://github.com/Mcourtyard/m-courtyard/tree/d560d1b1337a9c5f45724fb36b12e12d35c49372/app/src-tauri/src/commands) | Tauri IPC commands for project, dataset, training, inference, export, environment, storage, notification, and configuration flows |
| [`app/src-tauri/scripts/`](https://github.com/Mcourtyard/m-courtyard/tree/d560d1b1337a9c5f45724fb36b12e12d35c49372/app/src-tauri/scripts) | Python scripts for data cleaning, dataset generation, inference, export, and environment setup |
| [`CHANGELOG.md`](https://github.com/Mcourtyard/m-courtyard/blob/d560d1b1337a9c5f45724fb36b12e12d35c49372/CHANGELOG.md) | Release history for environment stability, notifications, export targets, training history, smart alerts, and local runtime support |

Relevant Melix baseline documents:

- [`current-status.md`](../current-status.md)
- [`architecture-spec.md`](../architecture-spec.md)
- [`benchmark-evaluation-contract.md`](../benchmark-evaluation-contract.md)
- [`agentic-trajectory-dataset-contract.md`](../agentic-trajectory-dataset-contract.md)
- [`unified-agentic-tool-runtime-contract.md`](../unified-agentic-tool-runtime-contract.md)
- [`evidence-telemetry-report-contract.md`](../evidence-telemetry-report-contract.md)
- [`reference-scans/sparrow-localai-lessons.md`](sparrow-localai-lessons.md)

## Positioning Comparison

Melix is a local-first AI runtime for Apple Silicon. It owns a Swift control
plane, Swift and Python workers, local model operations, server sessions, chat,
LoRA workflows, benchmark and evaluation workflows, evidence artifacts, and a
native macOS operator surface.

M-Courtyard is narrower and more guided. It focuses on a zero-code desktop path
for turning local documents into training datasets, running MLX fine-tuning,
testing the adapter, and exporting the result into local runtimes. The main
advantage is not raw runtime breadth; it is the tightly guided project
experience around local fine-tuning and the practical user safeguards around
environment setup, training visibility, export verification, and storage
cleanup.

Melix already has broader runtime architecture and stronger evidence contracts.
The improvement opportunity is to make the LoRA and dataset workflows feel as
coherent and self-guiding as the reference project while preserving Melix's
control-plane authority, schema-first artifacts, Apple Silicon observability,
and benchmark or evaluation evidence rules.

## Reference Advantages

| Advantage | Evidence | Value | Melix Improvement Direction |
|---|---|---|---|
| Guided end-to-end fine-tuning path | `README.md` describes a four-step path from raw documents to datasets, MLX fine-tuning, testing, and export. | Users do not have to compose separate CLI scripts, directories, and runtimes. | Add a project-centered LoRA workspace that connects dataset preparation, training, testing, export, and acceptance evidence. |
| Stable project artifact layout | `app/src-tauri/src/fs/project_dir.rs` creates `raw`, `cleaned`, `dataset`, `adapters`, and `logs` under each project. | Artifacts are easy to inspect, clean, and relate to one training run. | Define a Melix workspace manifest and artifact layout for training projects. |
| App-managed local Python and MLX setup | `environment.rs` creates a `uv` virtual environment and installs `mlx-lm[train]` plus document dependencies. | First-run setup is productized instead of left to support docs. | Add a Desktop and CLI environment doctor with repair receipts for Python, MLX, and dependency state. |
| Finder-launched app PATH recovery | `python/executor.rs` reads the user's login shell `PATH` before locating `uv` or `ollama`. | Packaged macOS apps can find tools installed by Homebrew, uv, or shell profiles. | Add GUI environment diagnostics for shell PATH, runtime binaries, and inherited variables. |
| Enterprise proxy and certificate support | `config.rs` persists proxy and certificate settings and passes them into `uv` commands. | Users behind corporate networks can install dependencies and download models. | Add network environment checks and redacted proxy/CA receipts to Melix settings and diagnostics. |
| Cross-runtime local model discovery | `training.rs` scans Hugging Face-style caches, ModelScope, Ollama, and LM Studio layouts. | Users can reuse models they already downloaded elsewhere. | Extend the model catalog with external runtime source descriptors and scan receipts. |
| Document ingest quality controls | `clean_data.py` supports privacy masking, exact and fuzzy deduplication, and extension-aware segmentation. | Training data quality improves before expensive generation or training starts. | Add dataset preparation controls for PII masking, deduplication, and segment strategy evidence. |
| Versioned generated datasets | `dataset.rs` creates timestamped dataset output directories with `meta.json`. | Operators can compare generated datasets and trace source files, mode, model, and settings. | Make dataset versions first-class Melix artifacts linked to training and evaluation runs. |
| Failed segment retry | `dataset.rs` can regenerate only failed dataset segments from a prior version. | Expensive generation runs can be repaired without starting over. | Add failed-only retry for synthetic dataset and evaluation-data generation. |
| Dataset quality summary | `generate_dataset.py` writes `quality.json` with score, grade, success rate, failed count, and output length. | Operators can judge whether a dataset is trainable before running LoRA. | Add a schema-backed dataset quality summary and report section. |
| Mode recommendation from content samples | `DataPrepPage.tsx` infers likely QA, style, chat, or instruction modes from source text. | Non-experts receive a practical default without reading a training guide. | Add a dataset mode advisor in the operator surface and CLI preflight. |
| Trainability guardrails | `training.rs` blocks full fine-tuning of quantized models before MLX raises a low-level error. | Known runtime incompatibilities become clear, early validation failures. | Encode trainability checks for model family, quantization, fine-tune type, sequence length, and memory fit. |
| Training metadata contract | `training.rs` writes `training_meta.json` with base model, fine-tune type, optimizer, LoRA settings, dataset path, sample counts, and creation time. | Export and history flows have a durable provenance source. | Define a Melix adapter provenance manifest consumed by publish, export, comparison, and reports. |
| Live training events and smart alerts | `training.rs` emits loss/progress events and detects OOM, Metal watchdog, and rising loss signatures. | Training failures are visible as product state, not just logs. | Parse training logs into structured run events and diagnostics. |
| Local training queue | `trainingQueueStore.ts` serializes training jobs and checks task admission before starting the next job. | Local resources are protected from accidental overlapping training runs. | Add durable queue admission and restore behavior for training jobs. |
| Multi-target export | `export.rs` supports Ollama, GGUF, MLX, and local inference server flows. | Fine-tuned models can leave the app in formats users already operate. | Add a runtime-aware export contract for Melix, Ollama, GGUF, and MLX artifacts. |
| Post-export smoke test | `export.rs` verifies exported Ollama models with metadata and generation checks. | Export success means the model can actually load and answer. | Require post-export load and generation checks before marking export complete. |
| Export failure diagnosis | `export.rs` tails Ollama logs and maps load failures to actionable messages. | Operators get a remedy instead of an opaque subprocess failure. | Add runtime-specific export diagnostic parsers and remediation hints. |
| Serve exported artifacts | `export.rs` can start and stop `mlx-lm.server` for an exported MLX model. | A trained artifact can be tested immediately through an OpenAI-compatible endpoint. | Add "serve this artifact" shortcuts backed by Melix session control. |
| Storage and cleanup visibility | `storage.rs` scans cache-like outputs and protects cleanup while tasks are active. | Large local artifacts can be cleaned deliberately without corrupting active work. | Add workspace, checkpoint, export, and runtime cache inventory with safe cleanup plans. |

## Milestone Mapping

The follow-up work is grouped into four milestones. Each milestone contains two
plans, and each plan is split into two independently executable units in
[`2026-05-24-m-courtyard-improvement-roadmap.md`](../plans/2026-05-24-m-courtyard-improvement-roadmap.md).

| Milestone | Reference Advantages Covered |
|---|---|
| M1 Guided Project Workspace and Dataset Preparation | guided end-to-end path, project artifact layout, document quality controls, dataset versions, failed retry, quality summary, mode recommendation |
| M2 Training Monitor and Adapter Provenance | trainability guardrails, training metadata, live events and smart alerts, local training queue |
| M3 Runtime-Aware Export and Serving Verification | multi-target export, post-export smoke test, export diagnostics, serve exported artifacts |
| M4 Local Runtime Integration, Environment, and Storage Operations | app-managed environment, GUI PATH recovery, proxy and certificate support, cross-runtime model discovery, storage cleanup |

## Adoption Guardrails

- Use the reference project as product evidence and workflow inspiration only.
- Do not copy AGPL-licensed implementation code or assets into Melix.
- Keep Melix's source of truth in the Swift control plane and schema-backed
  artifacts; do not introduce a parallel untyped project database as the
  authority.
- Keep Melix scoped to local-first Apple Silicon runtime workflows rather than
  becoming a generic desktop fine-tuning clone.
- Preserve existing Melix evidence rules: report JSON and run evidence remain
  the source of truth for benchmark, evaluation, export, and release claims.
- Every implementation issue created from this scan must define performance
  probes, measurement points, and success metrics before broad implementation.

## Probe And Metrics Expectations

This scan is documentation-only and adds no runtime probe. Follow-up
implementation plans must define their own probes before code changes.

Expected probe coverage by milestone:

| Milestone | Required Measurement Direction |
|---|---|
| M1 Guided Project Workspace and Dataset Preparation | workspace manifest validation latency, document ingest throughput, segmentation counts, PII mask count, dedup ratio, dataset version listing latency, failed retry success rate, quality scoring latency |
| M2 Training Monitor and Adapter Provenance | trainability preflight latency, queue admission latency, queue restore latency, log parser throughput, alert detection latency, adapter manifest write latency, loss-series row count |
| M3 Runtime-Aware Export and Serving Verification | export planning latency, artifact size, export duration, smoke-test load latency, generation latency, diagnostic parser coverage, exported artifact retention size |
| M4 Local Runtime Integration, Environment, and Storage Operations | external inventory scan latency, scan payload size, PATH/proxy/CA diagnostic latency, redaction coverage, storage inventory latency, cleanup dry-run latency, safe-delete count |

## Completion Criteria

This scan is complete when:

- the scan and execution roadmap are committed,
- both are linked from the documentation index,
- the follow-up milestone, plan, and unit issues are created and linked from
  the roadmap,
- each created issue is delegated to an agent for implementation readiness, and
- the pull request records the docs-only verification and metrics `N/A` reason.
