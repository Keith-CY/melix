# LoRA Training Story

## Narrative

The most important Melix story is the local adaptation loop:

1. Start from a base model that already runs on the Mac.
2. Bring a dataset package or Hugging Face dataset into the training workflow.
3. Train a LoRA or QLoRA adapter with explicit hyperparameters.
4. Activate the adapter as a named derived model.
5. Compare the base and derived models through benchmark and evaluation runs.
6. Keep the adapter package, derived-model receipt, exports, and screenshots as
   reproducible evidence.

This is the difference between "I tried a fine-tune once" and "I can operate a
local model improvement loop."

## Operator Flow

### 1. Inspect Adapters

```bash
swift run melix lora list --json
```

Use this before and after training to inspect adapter packages and activated
derived models.

### 2. Train An Adapter

```bash
swift run melix lora train \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --dataset-uri /absolute/path/to/dataset-package \
  --adapter-name melix-dev-adapter \
  --target-repo melix/adapters/melix-dev-adapter \
  --training-mode qlora \
  --rank 16 \
  --alpha 32 \
  --dropout 0.1 \
  --batch-size 4 \
  --epochs 1 \
  --learning-rate 1e-5 \
  --max-seq-length 2048 \
  --response-only \
  --mask-prompt
```

Melix validates the dataset, normalizes the training configuration, expands
family-aware target modules, runs the worker-owned training path, and writes a
`train_lora.adapter.json` package.

### 3. Train From A Hugging Face Dataset

```bash
swift run melix lora train \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --hf-dataset-path HuggingFaceH4/ultrachat_200k \
  --hf-train-split train_sft \
  --hf-valid-split test_sft \
  --chat-feature messages \
  --adapter-name melix-ultrachat \
  --target-repo melix/adapters/melix-ultrachat \
  --training-mode qlora
```

This is the public story for bringing a known dataset into the same local
adapter lifecycle without changing the operator surface.

### 4. Activate The Adapter

```bash
swift run melix lora activate \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --adapter-path /absolute/path/to/train_lora.adapter.json \
  --activation-mode adapter_backed_runtime \
  --alias melix-qwen35-acceptance
```

The activated model becomes a named derived model. It can be selected by the
server, benchmark, evaluation, and comparison surfaces.

### 5. Compare Base Versus Derived

```bash
swift run melix eval compare \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --target-model-id melix-qwen35-acceptance \
  --suite mmlu \
  --sample-size 4 \
  --scoring-mode multiple_choice_accuracy
```

The comparison step is the marketing-critical proof point: Melix does not stop
at training. It carries the derived model into the same evaluation and export
system used for the base model.

## App Story

The native App exposes the same workflow as the CLI:

- choose a base model
- choose a local package or Hugging Face dataset
- choose `LoRA` or `QLoRA` training mode (see the
  [LoRA runbook](../runbooks/phase-8-lora-adapter-workflow.md) for the full mode
  list)
- set adapter name, target repo, validation split, activation mode, and derived
  model alias
- train, inspect history, activate, compare, publish, or remove derived models

![Melix Window UI showing an active LoRA-derived local server](assets/window-ui-lora-workflow.png)

The screenshot above was generated from the current native App renderer after a
Window UI acceptance run trained and activated a derived model. It shows the
resulting local server with LoRA active.

## What To Emphasize

- The loop is local: dataset, adapter, derived model, benchmark, and evaluation
  artifacts stay on the machine.
- The loop is reproducible: smoke commands and acceptance bundles record job
  IDs, export paths, model IDs, and screenshot paths.
- The loop is operator-friendly: the CLI and native App route through the same
  product authority.
- The loop is honest: Melix records both positive paths and validation failures
  for missing model, adapter, compare target, and export data.
