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

- one-command combined benchmark plus evaluation runs
- leaderboard or community-submission APIs

## Product Split

### Performance Benchmarking

`bench` measures runtime serving behavior for a selected target.

It is responsible for:

- context-length sweep measurements
- continuous batching measurements
- runtime latency and throughput metrics
- task-aware runtime metrics such as preprocessing or artifact publication timing
- experimental matrix-style load exploration through a distinct command surface

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

`eval` v1 supports:

- `text-generation`
- `image-to-text`
- `image-text-to-text`

## Performance Benchmark Contract

Melix exposes two distinct performance workflows:

- `bench run`: operator-facing product benchmark
- `bench matrix run`: experimental performance matrix

The two workflows share target resolution and task kinds, but they do not share one request or export schema.

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

## Performance Matrix Contract

### Matrix Scope

`bench matrix` is a research-oriented performance workflow for controlled serving experiments.

It must not overload or silently alter the product-facing `bench run` contract.

Matrix v1 covers these task kinds:

- `text-generation`
- `image-to-text`
- `image-text-to-text`

Matrix v1 does not cover:

- `text-to-image`
- `image-text-to-image`

### Required Inputs

Every `bench matrix run` request must include:

- `target`: `model_id` or `hf_repo_id`
- `task_kind`
- at least one `suite_id`
- at least one `context_length`
- at least one `generation_length`
- at least one `batch_size`
- at least one `cache_profile`
- at least one `reasoning_mode`
- at least one `structured_output_mode`
- at least one `concurrency_level`
- `repeats`
- exactly one load budget:
  - `requests`
  - `duration_seconds`

### Normalized Input Fields

The canonical normalized matrix request shape is:

- `model_id: string`
- `hf_repo_id: string`
- `task_kind: string`
- `suite_ids: string[]`
- `context_lengths: int[]`
- `generation_lengths: int[]`
- `batch_sizes: int[]`
- `cache_profiles: string[]`
- `reasoning_modes: string[]`
- `structured_output_modes: string[]`
- `concurrency_levels: int[]`
- `repeats: int`
- `requests: int`
- `duration_seconds: int`

### Matrix Summary Outputs

Each completed matrix cell must persist one summary row with:

- `job_id`
- `task_kind`
- `source_repo`
- `model_id`
- `suite_id`
- `context_length`
- `generation_length`
- `batch_size`
- `cache_profile`
- `reasoning_mode`
- `structured_output_mode`
- `concurrency_level`
- `repeats`
- `requests`
- `duration_seconds`
- `ttft_mean_ms`
- `ttft_std_ms`
- `request_latency_mean_ms`
- `request_latency_std_ms`
- `prefill_tokens_per_second_mean`
- `decode_tokens_per_second_mean`
- `throughput_requests_per_second`
- `throughput_tokens_per_second`
- `success_rate`
- `peak_memory_bytes_max`
- `queue_wait_mean_ms`
- `queue_wait_p95_ms`
- `created_at_unix_ms`

### Matrix Request-Level Outputs

Each completed matrix request row must persist:

- `job_id`
- `cell_id`
- `task_kind`
- `suite_id`
- `context_length`
- `generation_length`
- `batch_size`
- `cache_profile`
- `reasoning_mode`
- `structured_output_mode`
- `concurrency_level`
- `repeat_index`
- `request_index`
- `ttft_ms`
- `request_latency_ms`
- `prefill_tokens_per_second`
- `decode_tokens_per_second`
- `queue_wait_ms`
- `peak_memory_bytes`
- `status`
- `error_code`
- `created_at_unix_ms`

### Matrix Export Formats

`bench matrix export-summary-csv` must emit one row per completed matrix cell using the matrix summary fields.

`bench matrix export-requests-csv` must emit one row per request observation using the matrix request-level fields.

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

Evaluation dataset overrides may also provide:

- `dataset_id`
- `dataset_root`

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
- `imagenette`
- `gsm8k`
- `humaneval`
- `mbpp`

Multimodal evaluation datasets must package media alongside `manifest.json` and `samples.jsonl`.
Relative media references are resolved against `dataset_root`.

### Evaluation Dataset Contract

Melix evaluation executes only against repository-owned evaluation dataset packages.

Every execution package must provide:

- `manifest.json`
- `samples.jsonl`

External datasets, including Hugging Face datasets, may be reused as source inputs, but they must
be materialized into a Melix evaluation dataset package before execution.

The authoritative runtime contract is the materialized evaluation package rather than any external
source schema.

### Planned Final-Result Evaluation Profile

This section defines the planned long-term contract for final-result evaluation. It is not yet
implemented by the current Melix runtime.

Every future-oriented evaluation dataset package is expected to declare a single evaluation profile
in `manifest.json` with these core fields:

- `profile_type: final_result`
- `result_kind: json | text`
- `extraction_mode: strict_full_response | heuristic_final`
- `scoring_mode`
- `threshold`

Future `final_result` sample rows use these fields:

- `system`
- `input`
- `target`

The future Melix execution contract remains the materialized evaluation package rather than any
external dataset schema.

#### Final-Result Principles

The `final_result` profile is the planned abstraction for future structured and non-structured LoRA
evaluation.

Its contract is intentionally narrow:

- only the extracted final result is scored
- `raw_response` is retained for debugging, not correctness scoring
- CoT or other wrapper text may appear in `raw_response`, but it is not itself evaluation evidence
- v1 covers ground-truth evaluation only; no-target or format-only evaluation is deferred
- task names such as `extraction`, `relationship`, and `summarization` remain suite metadata rather
  than scorer dispatch keys

#### Result Kinds

The planned v1 `result_kind` set is:

- `json`
- `text`

For `result_kind: json`:

- `target` must be valid JSON with root type `object` or `array`
- `output_schema` defines the accepted JSON root type and schema rules
- schema validation is required before scoring begins
- object roots are expected to support field-level comparison in v1
- array roots are expected to use conservative scoring in v1 rather than broad task-specific logic

The default ignored field set for JSON object scoring is:

- `evidence`
- `confidence`
- `closeness_logits`
- `closeness_probs`

Manifest-declared `ignored_paths` extend the default ignored field set. They do not override it.

For `result_kind: text`:

- `target` is the expected final text result after normalization
- v1 scoring is limited to stable text comparisons such as normalized exact match, label match, and
  regex match
- open-ended task-specific text scorers are out of scope for this contract

#### Extraction Modes

The runtime owns final-result extraction. Package-specific custom extractors are not part of the v1
contract.

`extraction_mode` defines how Melix isolates the final result from `raw_response`:

- `strict_full_response`: the full response must be the final result payload; wrapper prose causes
  extraction failure
- `heuristic_final`: Melix applies a shared runtime extractor ladder to locate the final result in a
  response that may include CoT or other wrapper text

`heuristic_final` must be deterministic and reproducible. Ambiguous extraction is a failure rather
than a guess.

For `result_kind: json`, the planned shared extractor ladder is:

- prefer the last contentful fenced `json` block
- otherwise use the last contentful fenced block whose contents parse as JSON
- otherwise use the last terminal balanced JSON suffix
- if multiple same-priority candidates remain, record `ambiguous_extraction`

For `result_kind: text`, the planned shared extractor ladder is:

- prefer the last terminal `Final answer:` or `Answer:` span
- otherwise use the last contentful fenced text block
- otherwise use the last terminal non-empty line or paragraph
- if multiple same-priority candidates remain, record `ambiguous_extraction`

The current PR direction of describing extraction as "last valid JSON value" is not stable enough
for the long-term contract because it is JSON-specific and under-specifies ambiguity handling.

#### Scoring Model

The planned execution pipeline is:

- capture `raw_response`
- extract `extracted_result`
- validate the extracted result for its declared `result_kind`
- normalize as required by `scoring_mode`
- score only the extracted result against `target`

In the future `final_result` path, correctness is computed from `extracted_result` rather than the
full response text.

Current repository fixtures still largely use `prompt` and `expected` sample rows. Those are
current-state implementation formats rather than the planned long-term `final_result` contract.

### Evaluation Summary Outputs

The fields below describe the current shipped summary and sample export contract. The future
`final_result` path is expected to extend this output surface with extraction- and
validation-oriented evidence such as `extracted_result`, `extraction_status`, `validation_status`,
`failure_reason`, `extraction_success_count`, and `validation_success_count`. Those additions are
planning direction only and are not implemented by the current runtime.

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
- `task_kind`
- `correct`
- `expected`
- `predicted`
- `question`
- `raw_response`
- `time_s`
- `parse_status`
- `input_modalities`
- `media_references`

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
- `task_kind`
- `correct`
- `expected`
- `predicted`
- `question`
- `raw_response`
- `time_s`
- `parse_status`
- `input_modalities`
- `media_references`

`eval export-samples-jsonl` must emit the same sample-level fields as line-delimited JSON objects.

## Run History Contract

Melix may present benchmark and evaluation history together in a common run browser, but the persisted run kind must be explicit.

Every persisted run summary must include:

- `run_kind`
- `benchmark_mode`
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

`benchmark_mode` must be one of:

- `standard`
- `matrix`

UI layers must not mix performance metrics and intelligence scores in one combined metric card set.

## Window UI Contract

The Window UI must expose separate operator surfaces for `bench` and `eval`.

### Performance Surface

The performance surface must expose:

- a `standard` or `matrix` mode selector
- target selection
- suite selection
- context-length controls
- batch-size controls
- summary metric cards
- context-sweep visualization
- batching-speedup visualization
- history
- summary CSV export

### Performance Matrix Surface

The matrix surface must expose:

- target selection
- suite selection
- context-length multi-select
- generation-length multi-select
- batch-size multi-select
- cache-profile multi-select
- reasoning-mode multi-select
- structured-output-mode multi-select
- concurrency multi-select
- repeats control
- one load budget selector with:
  - `requests`
  - `duration_seconds`
- matrix summary cards
- matrix summary table
- throughput and latency visualizations across selected dimensions
- matrix history
- summary CSV export
- request CSV export

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
- `melix bench matrix run`
- `melix bench matrix list`
- `melix bench matrix export-summary-csv`
- `melix bench matrix export-requests-csv`
- `melix eval run`
- `melix eval list`
- `melix eval export-summary-csv`
- `melix eval export-samples-csv`
- `melix eval export-samples-jsonl`

All commands must support `--json`.

Human-readable output is required by default.

## Forward Compatibility

Future benchmark work may extend `bench matrix` to additional task kinds or add release-gate integration, but it must preserve:

- the distinct `bench run` and `bench matrix` command surfaces
- the distinct standard and matrix export schemas
- explicit `benchmark_mode` persistence in shared run history
