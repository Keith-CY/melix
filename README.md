<p align="center">
  <img src="apps/macos-menubar/Sources/AppMain/Resources/Branding/melix_logo.svg" alt="Melix logo" width="180">
</p>

# Melix

[![release gates](https://img.shields.io/github/actions/workflow/status/Keith-CY/melix/release-gates.yml?branch=main&label=release%20gates)](https://github.com/Keith-CY/melix/actions/workflows/release-gates.yml)
[![app packaging](https://img.shields.io/github/actions/workflow/status/Keith-CY/melix/package-self-contained-app.yml?branch=main&label=app%20packaging)](https://github.com/Keith-CY/melix/actions/workflows/package-self-contained-app.yml)
![platform](https://img.shields.io/badge/platform-Apple%20Silicon-black)
![macOS](https://img.shields.io/badge/macOS-15%2B-000000)
![Swift](https://img.shields.io/badge/Swift-6-F05138)
![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB)
![focus](https://img.shields.io/badge/focus-LoRA%20%2B%20Bench%20%2F%20Eval-0F766E)
[![license](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

Melix is a local-first AI runtime for Apple Silicon. It combines a Swift control plane, a Python worker stack, a public CLI, and a native macOS operator surface so one machine can manage local model serving, LoRA training, and benchmark or evaluation workflows from the same runtime.

## What Melix Is

Melix is not just a thin local inference wrapper. The current repository is aimed at a practical local model-operations loop:

- import or download models into a local registry
- bind those models to managed server sessions
- run local chat and operator workflows through a shared control plane
- train and activate LoRA or QLoRA adapters
- benchmark, evaluate, compare, and export results from the same product surface

## Why Melix Exists

Local AI work on Apple Silicon often gets split across too many disconnected tools: one script for serving, another for LoRA training, a notebook for evaluation, and an ad hoc shell history for benchmarks. Melix is being built to keep those loops together.

The current product direction especially favors LoRA training and benchmark discipline:

- train adapters without leaving the local Melix workflow
- compare base and derived models through the same CLI and operator UI
- keep benchmark, matrix benchmark, and evaluation evidence in one repository-owned format
- turn repeatable local benchmarking into part of the product, not an afterthought

## Who It Is For

- Apple Silicon practitioners who want a local runtime instead of a remote-only workflow
- model engineers who need a repeatable loop for LoRA fine-tuning, comparison, and evaluation
- local AI product builders who want a same-host runtime with both CLI and operator surfaces
- contributors who care about typed protocols, reproducible runbooks, and productized local tooling

## What You Can Do Today

- manage model roots, inspect registry state, and download or import local models
- create, select, start, pause, resume, wake, and stop server sessions
- run local chat flows through the `melix` CLI and the macOS operator surface
- train, activate, publish, and remove derived LoRA-backed models
- run `bench`, `bench matrix`, `eval`, and `eval compare` workflows and export artifacts
- package Melix for local launch agents, Homebrew service use, or preview app-bundle delivery

## Quick Start

For the shortest repository setup path:

```bash
make bootstrap
make proto
make swift-test
make py-test
make integration-test
```

Then use:

- [Getting Started](docs/getting-started.md) for the local stack, operator app, and first CLI flows
- [Current Status](docs/current-status.md) for what is actually shipped today
- [Documentation Map](docs/README.md) for the deeper protocol, runbook, and plan structure

## Documentation

- [Getting Started](docs/getting-started.md)
- [Current Status](docs/current-status.md)
- [Contributing](docs/contributing.md)
- [Docs Map](docs/README.md)
- [Benchmark, Evaluation, and LoRA Runbook](docs/runbooks/benchmark-matrix-evaluation-and-lora.md)
- [Local Install Runbook](docs/runbooks/phase-8-local-install.md)
- [Packaging Targets](docs/runbooks/platform-packaging-targets.md)

## Contributing

Contributions are welcome. Start with [docs/contributing.md](docs/contributing.md) for the repository workflow, expected verification commands, documentation rules, and handoff expectations.

If a change alters behavior, update the relevant spec, runbook, roadmap, or plan in the same change. The README should stay focused on the project itself; operational detail belongs under `docs/`.

## License

Melix is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
