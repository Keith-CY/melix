# Melix Current Status

_Last updated: 2026-04-12_

---

## Summary

Melix is a production-ready local AI runtime for Apple Silicon. It covers the full local model-operations loop: model registry management, server session control, local chat, LoRA fine-tuning, and benchmark or evaluation workflows — all from a native macOS app and CLI.

The original Phase 0–8 productization roadmap is **complete**. The codebase is no longer an early-stage thin path; it is a productized local runtime with CLI-first authority and a native macOS operator surface.

---

## What Works Today

### Model Management
- Multi-root local registry discovery
- Import models from disk or download from Hugging Face Hub
- Inspect registry state from the CLI or operator app

### Server Sessions
- Create, update, select, start, pause, resume, wake, and stop server sessions
- Full session lifecycle visible from the `melix` CLI and macOS workspace

### Chat
- Local chat flows through the `melix` CLI
- Chat surface in the native macOS operator workspace
- Fully offline — no data leaves your machine

### LoRA & QLoRA Fine-Tuning
- Train LoRA and QLoRA adapters on custom datasets
- Activate adapters as named derived models
- Publish and remove derived models from the local registry
- Compare base and adapter-derived models side by side
- Architecture-aware LoRA target presets for stable dense text families (`llama`, `qwen`, `gemma`, `kimi`)

### Benchmarking & Evaluation
- Single-model and matrix benchmark runs
- Evaluation suites (MMLU and more)
- Compare and export results from the same product surfaces
- Results stored in a repository-owned format for reproducible comparisons

### Native macOS App
- Menubar status and quick access
- Full operator workspace for all of the above
- Backed by the same CLI-first authority as the terminal workflow

### Packaging & Install
- Launch agent for persistent local service
- Homebrew service integration
- Preview app-bundle delivery
- Automated release-gate and acceptance-evidence workflows

---

## Operator Surfaces

| Surface | What It Provides |
|---|---|
| `melix` CLI | The primary command-line interface for all workflows |
| macOS Menubar App | Native macOS UI for model ops, chat, LoRA, benchmarks, and evaluation |
| Local Control Plane API | Typed protocol surface for CLI and operator integration |

---

## Verified Acceptance Evidence

The repository records product-level evidence for:

- Deterministic LoRA CLI and Window UI acceptance smokes
- Phase 8 CLI acceptance bundle capture
- Phase 8 native Window UI acceptance bundle and screenshot capture
- Release-gate automation through the GitHub Actions workflow
- Full LoRA workflow path evidence (`dataset → train → activate → compare → publish`) captured as per-stage success/failure counters in the release gate `lora_path` section and as a `lora_capability` section in the Phase 8 acceptance bundle

The default verification contract is: `make proto` → `make py-test` → `make swift-test` → `make integration-test`. Check [`progress.md`](../progress.md) for any current local caveats before treating the full gate as clean.

---

## Honest Boundaries

These are the current limits of the product. They're intentional, not oversights.

| Boundary | Detail |
|---|---|
| **Apple Silicon only** | Melix is intentionally scoped to macOS on Apple Silicon. No cross-platform support is planned for the current scope. |
| **LoRA family coverage** | `llama`, `qwen`, `gemma`, and `kimi` are the stable dense-family path. `mixtral` and `qwen3moe` are experimental via MoE hooks. `deepseek-mla`, `mistral4`, `nemotron-h`, and embedding-family models are not yet productized for `train_lora`. |
| **Disk-streaming** | Documented and probed, but true SSD-backed runtime execution is not yet shipped. |
| **Historical plans** | The plan archive is broader than the curated product docs. Archived plans are engineering history — not every plan is equally product-ready. |
| **Progress log** | `progress.md` tracks active verification notes. Treat it as the operational truth for known local issues. |

---

## Best Entry Points

| Goal | Where to Go |
|---|---|
| Set up for the first time | [Getting Started](getting-started.md) |
| Understand the phase history | [Phase Roadmap](phase-roadmap.md) |
| Run benchmarks and evaluation | [Benchmark & LoRA Runbook](runbooks/benchmark-matrix-evaluation-and-lora.md) |
| Install as a local service | [Local Install Runbook](runbooks/phase-8-local-install.md) |
| Browse all documentation | [Docs Map](README.md) |
| Check the latest progress notes | [`progress.md`](../progress.md) |
