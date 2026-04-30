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
- request exports include phase probes for dataset materialization, prompt rendering, warmup,
  prefill, decode, token counts, cache-hit state, runtime kind, speculative decode acceptance and
  rollback, DFlash state, and failure stage
- summary exports include cell wall time, completed and failed request counts, and p50/p95 latency
  probes for faster cell-level regression triage
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

Executable-code example with a checked-in dev fixture:

```bash
swift run melix eval run \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --suite humaneval \
  --dataset-id humaneval.dev.v1 \
  --sample-size 5 \
  --code-exec-policy sandboxed
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
- `humaneval.dev.v1` and `mbpp.dev.v1` are checked-in executable-code fixtures under `services/mlx-worker-python/fixtures/evaluation/`
- relative `image_uri` entries inside multimodal datasets are resolved against the selected dataset root automatically
- use `--dataset-root /absolute/path/to/evaluation-package` only when you want to override the checked-in fixture bundle
- `--code-exec-policy sandboxed` is mandatory for `humaneval` and `mbpp`; Melix rejects those suites without it
- evaluation runs persist under `<jobs_root>/evaluation/runs/<job_id>/`
- sample JSONL and CSV exports now include `execution_status` plus `execution_metadata` for
  code-suite evidence and non-evidence states
- sample exports include phase probes for render, inference, extraction, validation, scoring,
  response size, extracted-result size, and failure stage

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
  --suite mbpp \
  --dataset-id mbpp.dev.v1 \
  --sample-size 12 \
  --batch-factor 2 \
  --seed 9 \
  --scoring-mode pass_at_1 \
  --code-exec-policy sandboxed
```

Important compare rules:

- `eval compare` still uses model IDs, not adapter paths
- every `--target-model-id` must already exist in the local catalog
- compare results persist through the same evaluation export bundle as `eval run`, but compare exports use dedicated compare subcommands
- compare sample exports preserve executable-code evidence for both the base and target responses when the suite executes code
- human-readable compare output now includes `verdict`, observed delta, bootstrap CI, analytical CI,
  and the configured effect threshold for each target model
- `improvement` and `regression` are only emitted when delta clears the effect threshold and both
  interval families remain on the same side of zero; otherwise the result is `inconclusive`

Export the resulting comparison evidence with the dedicated compare export commands:

```bash
swift run melix eval list --json

swift run melix eval compare export-summary-csv \
  --job-id <compare-job-id> \
  --output /tmp/melix-evaluation-compare-summary.csv

swift run melix eval compare export-samples-csv \
  --job-id <compare-job-id> \
  --output /tmp/melix-evaluation-compare-samples.csv

swift run melix eval compare export-samples-jsonl \
  --job-id <compare-job-id> \
  --output /tmp/melix-evaluation-compare-samples.jsonl
```

The exported compare summary CSV adds these release-facing columns:

- `effect_threshold`
- `verdict`
- `bootstrap_lower_bound`
- `bootstrap_upper_bound`
- `analytical_lower_bound`
- `analytical_upper_bound`

The exported compare sample rows also retain `category_label` and `subject_label` when the suite
material provides stable category metadata.

Benchmark and matrix workflows remain one target per run, so benchmark-to-benchmark comparison is
still a serial job review workflow using `bench list`, `bench matrix list`, and CSV exports across
job IDs.

## Generate A Local Benchmark/Evaluation Report

Use the same report builder as CI when you want to compare two local export bundles in the terminal.
The inputs can be a bundle file or a directory containing `benchmark-evaluation-export.json` or
`export-bundle.json`.

Example:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
  uv run --project services/mlx-worker-python \
  python scripts/benchmark_evaluation_report.py \
    --baseline /tmp/melix-base/benchmark-evaluation-export.json \
    --candidate /tmp/melix-head/benchmark-evaluation-export.json \
    --format terminal \
    --output-dir /tmp/melix-bench-eval-report
```

The command prints a terminal table and writes:

- `/tmp/melix-bench-eval-report/report.md`
- `/tmp/melix-bench-eval-report/report.json`

Markdown or JSON output can be printed directly:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
  uv run --project services/mlx-worker-python \
  python scripts/benchmark_evaluation_report.py \
    --baseline /tmp/melix-base \
    --candidate /tmp/melix-head \
    --format markdown
```

Report status is advisory. `warning` rows indicate direction-aware regressions, including latency,
failure, rejected-token, rollback, and DFlash rollback increases or throughput, accuracy,
acceptance-rate, and accepted-token decreases. `missing` rows show metrics present on only one side.
`not_comparable` rows show differing runtime metadata, neutral numeric probes, or zero-baseline
data. Only malformed inputs make the script exit non-zero.

## Pull Request Report Workflow

The `bench-eval-report` GitHub Actions workflow runs on pull-request open, reopen, synchronize, and
ready-for-review events.

The workflow:

- checks out the base SHA and PR head SHA on the same macOS runner
- runs the same benchmark, matrix, and evaluation smoke suite for both revisions
- defaults the CI runtime to the deterministic text backend so PR reports do not depend on a
  runner-local model checkout or Swift MLX metallib cache
- pins the deterministic dev-text model path to a slash-free logical value so legacy base-SHA
  control planes do not require live-model evidence for the seed dev model
- prebuilds the Swift worker and control plane before startup so worker readiness waits measure
  process readiness instead of cold Swift compilation
- isolates each run with a separate `MELIX_HOME`, `.runtime` tree, model-ops root, and HTTP port
- uploads base, head, and report artifacts
- updates one sticky pull-request comment marked with
  `<!-- melix-benchmark-evaluation-report -->`

The PR comment does not block merges on advisory regressions. It is intended to make performance and
accuracy changes visible during review while preserving the exported artifacts for deeper debugging.

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
