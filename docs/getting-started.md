# Melix Getting Started

This guide is the shortest path from a fresh checkout to a working local Melix development loop.

## Prerequisites

- macOS on Apple Silicon
- `swift`
- `python3`
- `uv`
- `protoc`
- `protoc-gen-swift` for Swift protobuf generation

## Bootstrap The Repository

Install the locked Python environment and local build support:

```bash
make bootstrap
```

Generate committed protocol artifacts:

```bash
make proto
```

Run the default repository verification gates:

```bash
make swift-test
make py-test
make integration-test
```

## Start The Deterministic Local Stack

Bring up the default local runtime stack:

```bash
bash scripts/dev_up.sh
```

Inspect the current server snapshot:

```bash
swift run melix server snapshot --json
```

Shut the stack down when you are done:

```bash
bash scripts/dev_down.sh
```

The deterministic path is the default repeatable development loop. For details on runtime layout,
environment exports, and alternate startup modes, see
[`docs/runbooks/phase-1-local-stack.md`](runbooks/phase-1-local-stack.md).

## Start The Full macOS Operator Surface

If you want the backend stack plus the built macOS operator app:

```bash
make swift-test
bash scripts/dev_app_up.sh
```

This path uses the already built Swift executables for the CLI, control plane, text worker, and
menubar app instead of rebuilding on every launch.

## First CLI Checks

Once the local stack is running, these are good first checks:

```bash
swift run melix server snapshot --json
swift run melix lora list --json
swift run melix bench list --json
swift run melix eval list --json
```

## LoRA, Benchmark, And Evaluation Quick Loop

Choose a local model ID from `melix server snapshot --json`, then run a minimal loop such as:

```bash
swift run melix lora train \
  --model-id <model-id> \
  --dataset-uri /absolute/path/to/dataset-package \
  --adapter-name melix-dev-adapter \
  --target-repo melix/adapters/melix-dev-adapter

swift run melix lora activate \
  --model-id <model-id> \
  --adapter-path /absolute/path/to/train_lora.adapter.json \
  --alias melix-dev-derived

swift run melix bench run \
  --model-id <model-id> \
  --suite smoke

swift run melix eval run \
  --model-id <model-id> \
  --suite mmlu
```

For the full operator flow, dataset expectations, matrix benchmark examples, CSV exports, and
compare workflows, use these runbooks:

- [`docs/runbooks/phase-8-lora-adapter-workflow.md`](runbooks/phase-8-lora-adapter-workflow.md)
- [`docs/runbooks/benchmark-matrix-evaluation-and-lora.md`](runbooks/benchmark-matrix-evaluation-and-lora.md)

## Install And Packaging Paths

If you want a local product-style install instead of the repository-local development loop, start
with:

- [`docs/runbooks/phase-8-local-install.md`](runbooks/phase-8-local-install.md)
- [`docs/runbooks/homebrew-install.md`](runbooks/homebrew-install.md)
- [`docs/runbooks/platform-packaging-targets.md`](runbooks/platform-packaging-targets.md)

## Read Next

- [`docs/current-status.md`](current-status.md)
- [`docs/contributing.md`](contributing.md)
- [`docs/README.md`](README.md)
