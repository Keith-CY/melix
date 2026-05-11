# Melix Overview

## Short Positioning

Melix is a native local AI operations workspace for Apple Silicon. It lets an
operator run models, fine-tune LoRA adapters, activate derived models, benchmark
results, and evaluate quality from one local CLI and macOS App.

## Product Introduction

Local model work often spreads across shell scripts, notebooks, temporary
folders, and one-off benchmark logs. Melix turns that loop into a productized
local workflow.

With Melix, the operator can import or download a model, start a local server,
chat with it, train a LoRA or QLoRA adapter on a local or Hugging Face dataset,
activate the adapter as a named derived model, and compare the result against
the base model. The same control plane backs the terminal workflow and the
native macOS App, so the CLI and App tell the same story.

Melix is intentionally local-first. Models, datasets, adapters, evaluation
results, benchmark exports, and App evidence stay on the Mac unless the operator
explicitly chooses to publish or export them.

## What Melix Does Today

| Capability | Product Meaning |
|---|---|
| Model registry | Discover, import, and manage local or Hugging Face models |
| Server sessions | Start, stop, pause, resume, and inspect local model servers |
| Chat | Run local chat from the CLI and native workspace |
| LoRA and QLoRA training | Train adapters on custom datasets and persist adapter packages |
| Adapter activation | Turn a trained adapter into a named derived model |
| Benchmarking | Run standard and matrix benchmarks with exportable results |
| Evaluation | Run quality suites and compare base versus derived models |
| Native App | Operate the workflow through a macOS menubar and workspace UI |

## Who It Is For

- Model engineers who want a repeatable local fine-tuning loop.
- Apple Silicon operators who want model serving, LoRA training, and evaluation
  in one place.
- Privacy-sensitive builders who need local datasets and local inference.
- Contributors who care about typed protocols, reproducible acceptance evidence,
  and product-grade local tooling.

## Hero Copy

**Your Mac. Your Models. Your Rules.**

Melix is a local AI workspace for Apple Silicon: run models, train LoRA
adapters, activate derived models, and compare the results without sending your
data to a remote service.

## Honest Boundaries

Melix is Apple Silicon first. Its stable LoRA training family coverage currently
focuses on dense text families such as `llama`, `qwen`, `gemma`, and `kimi`, with
selected MoE paths still marked experimental. Melix should not be described as a
cloud trainer, a cross-platform runtime, or a universal fine-tuning system for
every model family.

For the current shipped boundary, use [`docs/current-status.md`](../current-status.md)
as the source of truth.
