# Melix Benchmark And Evaluation Contract

## Purpose

Define the canonical product contract for Melix operator benchmarking after the split between:

- `bench`: performance benchmarking
- `eval`: intelligence evaluation

This specification defines the required inputs, outputs, persistence shape, and presentation rules for both product lines. It does not define implementation sequencing; execution planning remains under `docs/plans/`.

## Scope

This contract applies to:

- the public `melix` CLI
- the native Window UI
- control-plane request and response payloads
- persisted benchmark and evaluation runs
- export formats used for CSV and JSONL artifacts

This contract does not define:

- vision-language intelligence suites
- one-command combined benchmark plus evaluation runs
- research-only performance matrix workflows
- leaderboard or community-submission APIs

## Product Split

### Performance Benchmarking

`bench` measures runtime serving behavior for a selected target.

It is responsible for:

- context-length sweep measurements
- continuous batching measurements
- runtime latency and throughput metrics
- task-aware runtime metrics such as preprocessing or artifact publication timing

It is not responsible for:

- correctness scoring
- pass or fail judgments over benchmark datasets
- sample-level answer exports

### Intelligence Evaluation

`eval` measures correctness and reasoning quality for a selected target.

It is responsible for:

- benchmark-suite execution
- score aggregation
- category or subject breakdowns when supported
- sample-level evidence export

It is not responsible for:

- runtime throughput comparisons
- context sweep charts
- batching speedup charts

## Shared Target Model

Both product lines operate on the same benchmark target abstraction.

Each run must resolve exactly one target using one of these mutually exclusive selectors:

- `model_id`
- `hf_repo_id`

When `hf_repo_id` is used:

- the control plane must classify the imported target into a supported `task_kind`
- the imported target must appear in persisted run metadata as `source_repo`
- the control plane remains the orchestration truth for target resolution

## Task Kinds

Melix benchmark and evaluation targets use the following task-aligned values:

- `text-generation`
- `image-to-text`
- `image-text-to-text`
- `text-to-image`
- `image-text-to-image`

`bench` may support all task kinds.

`eval` v1 is intentionally limited to `text-generation`.

## Performance Benchmark Contract

### Required Inputs

Every `bench run` request must include:

- `target`: `model_id` or `hf_repo_id`
- `task_kind`
- at least one `suite_id`
- at least one `context_length`
- `generation_length`

Optional performance controls:

- `batch_sizes[]`
- `repeats`
- `cache_profile`
- `reasoning_mode`
- `structured_output_mode`

### Normalized Input Fields

The canonical normalized request shape is:

- `model_id: string`
- `hf_repo_id: string`
- `task_kind: string`
- `suite_ids: string[]`
- `context_lengths: int[]`
- `generation_length: int`
- `batch_sizes: int[]`
- `repeats: int`
- `cache_profile: string`
- `reasoning_mode: string`
- `structured_output_mode: string`

### Cache Profiles

`cache_profile` must be one of:

- `cold`
- `warm`
- `partial_prefix`

`partial_prefix` is reserved for realistic repeated-context performance measurement and must not be silently remapped to `warm`.

### Performance Outputs

Every completed `bench run` must persist:

- one run summary
- zero or more context-sweep rows
- zero or more batch-sweep rows
- task-aware summary metrics
- exportable CSV rows

### Summary Metrics

The summary metric set is:

- `prefill_tokens_per_second`
- `decode_tokens_per_second`
- `ttft_ms`
- `request_p50_ms`
- `request_p95_ms`
- `peak_memory_bytes`

Task-aware extensions:

- `preprocess_ms` for `image-to-text` and `image-text-to-text`
- `artifact_publish_ms` for `text-to-image` and `image-text-to-image`
- `output_bytes` for `text-to-image` and `image-text-to-image`

### Context-Sweep Rows

Each context-sweep row must include:

- `job_id`
- `task_kind`
- `suite_id`
- `context_length`
- `generation_length`
- `cache_profile`
- `prefill_tokens_per_second`
- `decode_tokens_per_second`
- `ttft_ms`
- `request_latency_ms`
- `peak_memory_bytes`
- `repeat_index`

### Batch-Sweep Rows

Each batch-sweep row must include:

- `job_id`
- `task_kind`
- `suite_id`
- `batch_size`
- `context_length`
- `generation_length`
- `decode_tokens_per_second`
- `prefill_tokens_per_second`
- `avg_ttft_ms`
- `request_latency_ms`
- `speedup_vs_batch_1`
- `repeat_index`

### Compatibility Aliases

For backward compatibility, persisted benchmark exports may continue to emit these aliases:

- `bench.smoke.tokens_per_second`
- `bench.smoke.ttft_ms`

These aliases are compatibility fields only. New UI surfaces and exports must prefer the canonical metric names defined above.

### Performance CSV Contract

`bench export-summary-csv` must emit one row per metric observation with these columns:

- `job_id`
- `task_kind`
- `source_repo`
- `model_id`
- `suite_id`
- `context_length`
- `batch_size`
- `generation_length`
- `cache_profile`
- `metric_name`
- `metric_value`
- `unit`
- `repeat_index`
- `created_at_unix_ms`

## Intelligence Evaluation Contract

### Required Inputs

Every `eval run` request must include:

- `target`: `model_id` or `hf_repo_id`
- one or more suite selections
- `sample_size`
- `batch_factor`

Optional evaluation controls:

- `few_shot`
- `seed`
- `scoring_mode`
- `code_exec_policy`

### Normalized Input Fields

The canonical normalized request shape is:

- `model_id: string`
- `hf_repo_id: string`
- `task_kind: string`
- `suite_ids: string[]`
- `sample_size: int`
- `batch_factor: int`
- `few_shot: int`
- `seed: int`
- `scoring_mode: string`
- `code_exec_policy: string`

### Initial Suite Set

The first canonical `eval` suite set is:

- `mmlu`
- `arc_challenge`
- `hellaswag`
- `winogrande`
- `truthfulqa_mc`
- `gsm8k`
- `humaneval`
- `mbpp`

### Evaluation Summary Outputs

Each completed suite result must include:

- `job_id`
- `model_id`
- `source_repo`
- `task_kind`
- `suite_id`
- `dataset_id`
- `score_name`
- `score_value`
- `sample_size`
- `correct_count`
- `incorrect_count`
- `duration_seconds`
- `created_at_unix_ms`

### Category Breakdown

When the suite supports category or subject scoring, the result must also include:

- `category_scores: { [category_name]: number }`

Absence of category support must be represented by omission rather than an empty map.

### Sample-Level Outputs

Each sample-level row must include:

- `id`
- `correct`
- `expected`
- `predicted`
- `question`
- `raw_response`
- `time_s`
- `parse_status`

`parse_status` is required in Melix even when the source benchmark does not expose it directly. This field provides operator-visible debugging for extraction failures and scorer fallbacks.

### Evaluation Export Formats

`eval export-summary-csv` must emit one row per suite result with these columns:

- `job_id`
- `task_kind`
- `source_repo`
- `model_id`
- `suite_id`
- `dataset_id`
- `score_name`
- `score_value`
- `sample_size`
- `correct_count`
- `incorrect_count`
- `duration_seconds`
- `created_at_unix_ms`

`eval export-samples-csv` must emit one row per evaluated sample with these columns:

- `job_id`
- `suite_id`
- `id`
- `correct`
- `expected`
- `predicted`
- `question`
- `raw_response`
- `time_s`
- `parse_status`

`eval export-samples-jsonl` must emit the same sample-level fields as line-delimited JSON objects.

## Run History Contract

Melix may present benchmark and evaluation history together in a common run browser, but the persisted run kind must be explicit.

Every persisted run summary must include:

- `run_kind`
- `job_id`
- `model_id`
- `source_repo`
- `task_kind`
- `status`
- `created_at_unix_ms`
- `updated_at_unix_ms`
- `output_dir`

`run_kind` must be one of:

- `benchmark`
- `evaluation`

UI layers must not mix performance metrics and intelligence scores in one combined metric card set.

## Window UI Contract

The Window UI must expose separate operator surfaces for `bench` and `eval`.

### Performance Surface

The performance surface must expose:

- target selection
- suite selection
- context-length controls
- batch-size controls
- summary metric cards
- context-sweep visualization
- batching-speedup visualization
- history
- summary CSV export

### Evaluation Surface

The evaluation surface must expose:

- target selection
- suite selection
- sample-size control
- batch-factor control
- optional few-shot and seed controls
- summary score cards
- suite comparison table
- sample preview
- summary CSV export
- sample CSV export
- sample JSONL export

## CLI Contract

The public CLI surface is:

- `melix bench run`
- `melix bench list`
- `melix bench export-summary-csv`
- `melix eval run`
- `melix eval list`
- `melix eval export-summary-csv`
- `melix eval export-samples-csv`
- `melix eval export-samples-jsonl`

All commands must support `--json`.

Human-readable output is required by default.

## Forward Compatibility

Melix may add a research-oriented performance matrix workflow in the future, but that workflow must not overload the operator-facing `bench run` contract defined here.

If added later, that workflow must use a distinct command surface and a distinct export schema.
