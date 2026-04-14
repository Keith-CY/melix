# Benchmark, Matrix, Evaluation, And LoRA Comparison Workflow

## Purpose

Run Melix standard benchmarks, matrix benchmarks, and evaluation suites from the native operator
window or the public `melix` CLI, then compare base models and LoRA-derived models through the same
execution surface.

This runbook is intentionally execution-focused. It explains:

- how to choose a target model or direct Hugging Face repo
- how to run standard `bench` jobs
- how to run `bench matrix` sweeps
- how to run `eval` jobs
- how to use LoRA adapters with those workflows
- how to run first-class `eval compare` jobs against activated derived models

## Preconditions

- `make bootstrap` has completed successfully
- `make proto` has completed successfully
- the local Melix stack is available
- you know whether you want to target:
  - a local Melix model or activated derived model
  - a direct Hugging Face repo
- if you want LoRA-backed comparisons, you already have either:
  - a checked local training dataset package
  - a supported Hugging Face dataset configuration

## Choose A Target

Melix benchmark and evaluation commands always target exactly one of:

- `--model-id` for a local catalog model, including a LoRA-derived model activated into the catalog
- `--repo-id` for a direct Hugging Face benchmark or evaluation target

Use the server snapshot to inspect local model IDs:

```bash
swift run melix server snapshot --json
```

Use the LoRA registry snapshot to inspect adapters and activated derived models:

```bash
swift run melix lora list --json
```

Important target-selection rules:

- `melix bench run` requires exactly one of `--model-id` or `--repo-id`
- `melix bench matrix run` requires exactly one of `--model-id` or `--repo-id`
- `melix eval run` requires exactly one of `--model-id` or `--repo-id`
- `melix eval compare` requires exactly one base target (`--model-id` or `--repo-id`) plus at least one `--target-model-id`
- benchmark, matrix, and evaluation do not accept an adapter path or adapter ID directly

## Run A Standard Benchmark

Use `bench run` for one benchmark job against one target with optional context, generation, batch,
and reproducibility controls.

Example:

```bash
swift run melix bench run \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --suite smoke \
  --suite latency \
  --context-length 1024 \
  --context-length 4096 \
  --generation-length 256 \
  --batch-size 2 \
  --batch-size 4 \
  --repeats 3 \
  --cache-profile partial_prefix \
  --reasoning-mode enabled \
  --structured-output-mode json_schema \
  --sample-size 6 \
  --batch-factor 2
```

Alternative direct-repo example:

```bash
swift run melix bench run \
  --repo-id unsloth/gemma-4-E4B-it-MLX-8bit \
  --suite smoke \
  --sample-size 4 \
  --batch-factor 1
```

History and export:

```bash
swift run melix bench list
swift run melix bench list --json

swift run melix bench export-csv \
  --job-id <benchmark-job-id> \
  --output /tmp/melix-benchmark.csv
```

Notes:

- `bench list` is the easiest way to recover persisted `job_id` values
- standard benchmark CSV export is `export-csv`
- standard benchmark runs persist under `<jobs_root>/bench/runs/<job_id>/`

## Run A Matrix Benchmark

Use `bench matrix run` when you want a controlled sweep over multiple dimensions instead of one
single benchmark configuration.

Required sweep dimensions:

- at least one `--suite`
- at least one `--context-length`
- at least one `--generation-length`
- at least one `--batch-size`
- at least one `--cache-profile`
- at least one `--reasoning-mode`
- at least one `--structured-output-mode`
- at least one `--concurrency`
- exactly one load budget:
  - `--requests`
  - `--duration-seconds`

Example:

```bash
swift run melix bench matrix run \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --suite smoke \
  --suite latency \
  --context-length 1024 \
  --context-length 4096 \
  --generation-length 128 \
  --generation-length 256 \
  --batch-size 1 \
  --batch-size 2 \
  --cache-profile cold \
  --cache-profile warm \
  --reasoning-mode disabled \
  --reasoning-mode enabled \
  --structured-output-mode plain_text \
  --structured-output-mode json_schema \
  --concurrency 1 \
  --concurrency 2 \
  --repeats 2 \
  --requests 24
```

History and exports:

```bash
swift run melix bench matrix list
swift run melix bench matrix list --json

swift run melix bench matrix export-summary-csv \
  --job-id <matrix-job-id> \
  --output /tmp/melix-benchmark-matrix-summary.csv

swift run melix bench matrix export-requests-csv \
  --job-id <matrix-job-id> \
  --output /tmp/melix-benchmark-matrix-requests.csv
```

Notes:

- use the summary CSV for cell-level comparisons
- use the requests CSV for request-level latency and throughput inspection
- matrix runs persist under `<jobs_root>/bench/matrix-runs/<job_id>/`

## Run An Evaluation Suite

Use `eval run` for quality-style checks over repository-owned evaluation suites.

Example with explicit suite and controls:

```bash
swift run melix eval run \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --suite mmlu \
  --suite gsm8k \
  --sample-size 12 \
  --batch-factor 2 \
  --few-shot 4 \
  --seed 9 \
  --scoring-mode multiple_choice_accuracy
```

Example for a code-evaluation suite:

```bash
swift run melix eval run \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --suite mbpp \
  --sample-size 12 \
  --seed 9 \
  --code-exec-policy sandboxed
```

Example with a checked-in image evaluation fixture:

```bash
swift run melix eval run \
  --repo-id mlx-community/paligemma2-3b-ft-docci-448-8bit \
  --suite imagenette \
  --sample-size 10
```

History and exports:

```bash
swift run melix eval list
swift run melix eval list --json

swift run melix eval export-summary-csv \
  --job-id <evaluation-job-id> \
  --output /tmp/melix-evaluation-summary.csv

swift run melix eval export-samples-csv \
  --job-id <evaluation-job-id> \
  --output /tmp/melix-evaluation-samples.csv

swift run melix eval export-samples-jsonl \
  --job-id <evaluation-job-id> \
  --output /tmp/melix-evaluation-samples.jsonl
```

Notes:

- if you omit `--suite`, the CLI defaults to `mmlu`
- if you omit `--dataset-id`, the CLI defaults to `<suite>.dev.v1`
- `few_shot` uses the same seeded dataset package as the scored samples; demo rows are excluded
  from the scored `sample_size`
- `seed` controls deterministic package ordering and is also forwarded to worker sampling where the
  runtime supports it
- `multiple_choice_accuracy` and `exact_match` are the current text scorer options; `pass_at_1`
  is reserved for `humaneval` and `mbpp`
- `--code-exec-policy sandboxed` is only valid for executable code suites such as `humaneval` and
  `mbpp`
- the current `sandboxed` implementation uses macOS `sandbox-exec`, runs inside a dedicated
  temporary directory, blocks network access, and enforces bounded stdout plus stderr capture
- if the worker cannot provide the `sandboxed` boundary, the evaluation request is rejected before
  candidate code is executed
- `mmlu.vision.dev.v1` is a checked-in image evaluation fixture under `services/mlx-worker-python/fixtures/evaluation/`
- `imagenette.dev.v1` is a checked-in 10-sample validation subset sourced from `frgfm/imagenette` (`160px`, validation split, Apache-2.0)
- relative `image_uri` entries inside multimodal datasets are resolved against the selected dataset root automatically
- use `--dataset-root /absolute/path/to/evaluation-package` only when you want to override the checked-in fixture bundle
- evaluation runs persist under `<jobs_root>/evaluation/runs/<job_id>/`
- sample JSONL and CSV exports now include `execution_status` plus `execution_metadata` for
  code-suite evidence and non-evidence states

## Planned Final-Result Evaluation Workflow

This section describes planned future direction rather than a shipped command path.

For LoRA workflows, the long-term Melix evaluation target is final-result quality rather than CoT
quality. A model may emit CoT or other wrapper text, but compare and eval should score only the
final extracted result.

That future path is not limited to schema-constrained JSON. The planned v1 final-result contract
covers:

- `json` final results, scored after extraction and schema-aware validation
- `text` final results, scored after extraction and stable text normalization

The future evidence model will expand from binary correct or incorrect counts alone to a layered
view of:

- extraction success
- validation success
- typed score against ground truth

Hugging Face datasets remain reusable source corpora, but not direct execution contracts. Planned
future execution will still require materialization into a Melix evaluation package before `eval`
or `compare` runs.

See these planning documents for the target contract and milestone sequence:

- `docs/superpowers/specs/2026-04-13-structured-output-evaluation-profile-design.md`
- `docs/plans/2026-04-13-structured-output-evaluation-roadmap.md`

## Use LoRA With Benchmark, Matrix, Evaluation, And Compare

LoRA adapters are not direct benchmark or evaluation targets. Melix benchmark and evaluation
commands operate on catalog model IDs or direct Hugging Face repos, so LoRA workflows must first
materialize or register a derived model ID.

The required workflow is:

1. Train an adapter package.
2. Activate that adapter into a derived text model.
3. Read the activated derived model ID from the LoRA registry snapshot.
4. Run `bench`, `bench matrix`, or `eval` against that derived `--model-id`.

### Train An Adapter

Local dataset package example:

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

Hugging Face dataset example:

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

### Activate The Adapter

```bash
swift run melix lora activate \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --adapter-path /absolute/path/to/train_lora.adapter.json \
  --activation-mode adapter_backed_runtime \
  --alias melix-qwen35-acceptance
```

Activation writes a derived-model manifest and registers a new text model into the local catalog.
`fused_derived_model` remains the default; `adapter_backed_runtime` is also supported when you
want runtime-bound activation without a fused local serving tree.

### Find The Derived Model ID

Use JSON output so you can read both adapter rows and derived model rows:

```bash
swift run melix lora list --json
```

Read:

- `adapters[*].adapter_name`
- `adapters[*].derived_model_id`
- `derived_models[*].model_id`
- `derived_models[*].adapter_name`

Important note:

- the activation alias is display metadata
- benchmark, matrix, and evaluation still require the actual derived `model_id`

### Run Benchmark, Matrix, Or Evaluation Against The Derived Model

Standard benchmark:

```bash
swift run melix bench run \
  --model-id <derived-model-id> \
  --suite smoke \
  --sample-size 6 \
  --batch-factor 2
```

Matrix benchmark:

```bash
swift run melix bench matrix run \
  --model-id <derived-model-id> \
  --suite latency \
  --context-length 2048 \
  --generation-length 256 \
  --batch-size 4 \
  --cache-profile warm \
  --reasoning-mode disabled \
  --structured-output-mode json_schema \
  --concurrency 2 \
  --duration-seconds 45
```

Evaluation:

```bash
swift run melix eval run \
  --model-id <derived-model-id> \
  --suite mmlu \
  --sample-size 12 \
  --batch-factor 2 \
  --few-shot 4 \
  --seed 9
```

### Remove A Derived Model When The Comparison Is Done

```bash
swift run melix lora remove-derived \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --derived-model-id <derived-model-id>
```

Melix removes the product-owned derived model artifacts and prunes the removed model from the
catalog snapshot. If you keep multiple adapters active in the catalog, remove each derived model
explicitly when the session is complete.

## Run Evaluation Compare Against Activated Derived Models

Use `eval compare` when you want one base target and one or more activated derived models in the
same evaluation job.

Example:

```bash
swift run melix eval compare \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --target-model-id <adapter-a-derived-model-id> \
  --target-model-id <adapter-b-derived-model-id> \
  --suite mmlu \
  --sample-size 12 \
  --batch-factor 2 \
  --few-shot 4 \
  --seed 9 \
  --scoring-mode multiple_choice_accuracy \
  --code-exec-policy sandboxed
```

Important compare rules:

- `eval compare` still uses model IDs, not adapter paths
- every `--target-model-id` must already exist in the local catalog
- compare results persist through the same evaluation history and export bundle as `eval run`

Export the resulting comparison evidence with the normal evaluation export commands:

```bash
swift run melix eval list --json

swift run melix eval export-summary-csv \
  --job-id <compare-job-id> \
  --output /tmp/melix-evaluation-compare-summary.csv

swift run melix eval export-samples-jsonl \
  --job-id <compare-job-id> \
  --output /tmp/melix-evaluation-compare-samples.jsonl
```

Benchmark and matrix workflows remain one target per run, so benchmark-to-benchmark comparison is
still a serial job review workflow using `bench list`, `bench matrix list`, and CSV exports across
job IDs.

## Native Operator Window Equivalents

Use the native operator window when you prefer interactive controls over CLI flags.

The current product surface exposes:

- a standard benchmark flow with suite and parameter controls
- a matrix benchmark flow with load-budget and sweep controls
- an evaluation flow with `Standard` and `Compare` modes, compare-target selection, sample-size, few-shot, seed, scoring, and code-exec controls
- LoRA training, activation, publish, and remove-derived tooling
- persisted history review and CSV export

The same target model rule still applies in the operator window:

- benchmark, matrix, and evaluation select a model or direct repo target
- LoRA must be activated first so the derived model appears as a selectable target

## Recommended Verification Sequence

For a reproducible end-to-end comparison session:

```bash
make bootstrap
make proto

swift run melix lora train \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --dataset-uri /absolute/path/to/dataset-package \
  --adapter-name melix-dev-adapter \
  --target-repo melix/adapters/melix-dev-adapter \
  --training-mode qlora

swift run melix lora activate \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --adapter-path /absolute/path/to/train_lora.adapter.json \
  --activation-mode adapter_backed_runtime \
  --alias melix-qwen35-acceptance

swift run melix lora list --json

swift run melix bench run \
  --model-id <derived-model-id> \
  --suite smoke \
  --sample-size 6 \
  --batch-factor 2

swift run melix bench matrix run \
  --model-id <derived-model-id> \
  --suite latency \
  --context-length 2048 \
  --generation-length 256 \
  --batch-size 4 \
  --cache-profile warm \
  --reasoning-mode disabled \
  --structured-output-mode json_schema \
  --concurrency 2 \
  --requests 12

swift run melix eval run \
  --model-id <derived-model-id> \
  --suite mmlu \
  --sample-size 12 \
  --batch-factor 2 \
  --few-shot 4 \
  --seed 9

swift run melix eval compare \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --target-model-id <derived-model-id> \
  --suite mmlu \
  --sample-size 12 \
  --batch-factor 2 \
  --few-shot 4 \
  --seed 9
```

## Related Runbooks

- `docs/runbooks/phase-8-lora-adapter-workflow.md`
- `docs/runbooks/m7-benchmark-and-evaluation-foundation.md`
