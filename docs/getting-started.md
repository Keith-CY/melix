# Getting Started with Melix

This guide walks you from a fresh checkout to a fully running local Melix stack. Most people are up and running in under ten minutes.

---

## What You Need

Before you begin, make sure your machine has:

| Requirement | Why |
|---|---|
| **macOS 15+** on **Apple Silicon** | Melix is built specifically for the Apple Silicon neural engine and runs natively on M-series Macs |
| **Swift** | Powers the Melix CLI, control plane, and menubar app |
| **Python 3.12+** | Powers the local model worker stack |
| **[uv](https://docs.astral.sh/uv/)** | Fast Python environment and package manager used by Melix |

> **No `protoc` needed.** `make proto` uses the pinned generators from the repository's locked dependencies — nothing extra to install.

---

## Step 1 — Bootstrap the Repository

Install the locked Python environment and local build support:

```bash
make bootstrap
```

Then generate the committed protocol artifacts (the typed message definitions that the CLI, control plane, and worker all share):

```bash
make proto
```

---

## Step 2 — Run the Verification Gates

Confirm everything is wired up correctly:

```bash
make swift-test
make py-test
make integration-test
```

All three should pass on a clean checkout. If something fails, check [Current Status](current-status.md) for known local issues before digging in.

---

## Step 3 — Start the Local Stack

Bring up the default local runtime:

```bash
bash scripts/dev_up.sh
```

Verify the stack is running:

```bash
swift run melix server snapshot --json
```

You should see a JSON snapshot of the current server state. When you're done:

```bash
bash scripts/dev_down.sh
```

For details on the runtime layout, environment exports, and alternate startup modes, see the [Local Stack Runbook](runbooks/phase-1-local-stack.md).

---

## Step 4 — Launch the Native macOS App *(optional)*

If you want the full macOS operator experience alongside the backend stack:

```bash
make swift-test
bash scripts/dev_app_up.sh
```

This starts the CLI, control plane, text worker, and menubar app using already-built Swift executables — no rebuild on every launch.

---

## First CLI Commands

Once the stack is running, these are the essential first checks:

```bash
# See all running server sessions and registered models
swift run melix server snapshot --json

# List trained LoRA adapters
swift run melix lora list --json

# List benchmark runs
swift run melix bench list --json

# List evaluation runs
swift run melix eval list --json
```

---

## Your First LoRA + Benchmark Loop

Pick a model ID from `melix server snapshot --json`, then run a minimal fine-tuning and evaluation loop:

```bash
# Train a LoRA adapter on your dataset
swift run melix lora train \
  --model-id <model-id> \
  --dataset-uri /absolute/path/to/dataset-package \
  --adapter-name my-adapter \
  --target-repo melix/adapters/my-adapter

# Activate the adapter as a named derived model
swift run melix lora activate \
  --model-id <model-id> \
  --adapter-path /absolute/path/to/train_lora.adapter.json \
  --alias my-derived-model

# Run a quick benchmark
swift run melix bench run \
  --model-id <model-id> \
  --suite smoke

# Run an evaluation
swift run melix eval run \
  --model-id <model-id> \
  --suite mmlu
```

For the full operator flow — dataset expectations, matrix benchmarks, CSV exports, and compare workflows — use these runbooks:

- [LoRA Adapter Workflow](runbooks/phase-8-lora-adapter-workflow.md)
- [Benchmark, Matrix & Evaluation Runbook](runbooks/benchmark-matrix-evaluation-and-lora.md)

---

## Installing Melix Locally

Prefer a product-style install over the repository development loop? These runbooks cover it:

- [Local Install Runbook](runbooks/phase-8-local-install.md) — Launch agent and persistent local service
- [Homebrew Install](runbooks/homebrew-install.md) — Homebrew-based service management
- [Packaging Targets](runbooks/platform-packaging-targets.md) — All delivery options at a glance

---

## What to Read Next

- [Current Status](current-status.md) — What's shipped today and where the honest limits are
- [Contributing](contributing.md) — How to contribute to Melix
- [Docs Map](README.md) — The full documentation index
