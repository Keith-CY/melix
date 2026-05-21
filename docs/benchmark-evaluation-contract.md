# Melix Benchmark And Evaluation Contract

## Purpose

Define the canonical product contract for Melix operator benchmarking after the split between:

- `bench`: performance benchmarking
- `eval`: intelligence evaluation

This specification defines the required inputs, outputs, persistence shape, and presentation rules for both product lines. It does not define implementation sequencing; execution planning remains under `docs/plans/`.

Structured run evidence, probe timelines, Apple Silicon telemetry, report JSON,
and PR or release-gate verification are governed by
`docs/evidence-telemetry-report-contract.md`. This document remains the domain
contract for benchmark and evaluation semantics; the evidence contract defines
how those results become auditable operator and release artifacts. For new
evidence and report artifacts, the evidence contract is authoritative and does
not inherit legacy export compatibility allowances documented later in this
file.

## Scope

This contract applies to:

- the public `melix` CLI
- the native Window UI
- control-plane request and response payloads
- persisted benchmark and evaluation runs
- combined benchmark and evaluation batch-run planning artifacts
- export formats used for CSV and JSONL artifacts

This contract does not define:

- leaderboard or community-submission APIs

## Combined Batch Run Planning

Melix may expose `melix batch run` as an operator-facing orchestration surface
for repeated benchmark plus evaluation sweeps over a model list. This surface
does not replace the canonical `bench` and `eval` product semantics; it plans,
records, and dispatches those existing product commands for each selected
model.

The supported batch commands are:

- `melix batch run --models <path> --dry-run`
- `melix batch run --models <path>`
- `melix batch status --run-id <id>`
- `melix batch status --temp-root <path>`
- `melix batch resume --run-id <id>`
- `melix batch resume --temp-root <path> --eval-only`

The dry-run mode must not contact Hugging Face, start a Melix runtime stack, or
submit benchmark or evaluation jobs. It must validate and normalize inputs,
materialize planning artifacts, and print a compact terminal summary.

The non-dry-run mode must execute one model at a time, update the manifest after
each stage, export benchmark and evaluation artifacts as soon as their jobs
complete, and keep an operator-visible bundle under `output_root` synchronized
with the temporary run directory.

### Model List Contract

The model list is a UTF-8 text file. Each non-empty, non-comment line selects
one model. Melix must preserve duplicate entries because repeated runs may be
intentional for reliability or variance checks.

Supported line forms are:

- `<hf_repo_id>`
- `<model_index>|<hf_repo_id>`

For lines without an explicit index, Melix assigns a zero-padded two digit
index in file order. Explicit indexes are preserved as provided. The normalized
model entry must include:

- `index`
- `repo_id`
- `source_line`

Subset selection uses 1-based model-list positions, not the model entry's
display `index` value. `start_index: 2` starts with the second selected line in
the normalized model list even when explicit display indexes are non-numeric or
non-contiguous.

Artifact and manifest identity uses the tuple `index`, `repo_id`, and
`source_line`. This keeps duplicate explicit entries isolated even when an
operator intentionally repeats the same display index and repo id. Per-model
artifact directory slugs must include the source line so repeated rows never
overwrite each other's command receipts, exports, or raw artifacts.

### Effective Configuration

Batch-run planning must resolve one effective configuration before any per-model
work begins. Resolution precedence is:

1. CLI option
2. config file value
3. environment variable
4. Melix default

The effective configuration artifact must be written as
`effective-config.json` in both the temporary run directory and the operator
output directory. It must include at least:

- `schema_version`
- `run_id`
- `model_list`
- `output_root`
- `temp_root`
- `start_index`
- `max_models`
- `selected_model_count`
- `total_model_count`
- `is_subset_run`
- `dry_run`
- `continue_on_failure`
- `restart_stack_per_model`
- `judge`
- `benchmark`
- `evaluation`
- `models`

### Batch Configuration File

`melix batch run --config <path>` accepts a minimal UTF-8 YAML subset for
operator-authored batch configuration. The supported subset is intentionally
limited to top-level `key: value` scalar entries; nested objects, lists, anchors,
and raw secret material are outside the batch-run config contract.

The supported config file keys are:

| Key | CLI Option | Environment Variable | Default | Purpose |
|---|---|---|---|---|
| `model_list` | `--models` | `MELIX_BATCH_MODEL_LIST` | required | Path to the UTF-8 model list. |
| `run_id` | `--run-id` | `MELIX_RUN_ID` | UTC timestamp `yyyyMMdd-HHmmss` | Stable run identifier. |
| `output_root` | `--output-root` | `MELIX_DOWNLOAD_ROOT` | `~/Downloads/melix-bench-eval-<run_id>` | Operator-visible bundle root. |
| `temp_root` | `--temp-root` | `MELIX_RUN_TMP_ROOT` | `.runtime/bench-eval-run/<run_id>` | Worktree-local scratch run root. |
| `melix_home` | config only | `MELIX_HOME` | `.runtime/home-<service_instance_name>` | Isolated Melix home used by health checks and later execution. |
| `runtime_dir` | config only | `MELIX_RUNTIME_DIR` | `.runtime/sidecars/<service_instance_name>` | Isolated runtime metadata directory. |
| `service_instance_name` | config only | `MELIX_SERVICE_INSTANCE_NAME` | `bench-eval-batch` | Local stack instance label. |
| `http_port` | config only | `MELIX_HTTP_PORT` | `12436` | Local HTTP port preflight value. |
| `melix_cli` | config only | `MELIX_CLI` | `<repo_root>/.build/debug/melix` | CLI artifact checked before long runs. |
| `start_index` | `--start-index` | `MELIX_START_INDEX` | `1` | 1-based model-list position to start from. |
| `max_models` | `--max-models` | `MELIX_MAX_MODELS` | `0` | Maximum selected models; `0` means all remaining. |
| `judge_remote_server_id` | `--judge-remote-server-id` | `MELIX_JUDGE_SERVER_ID` | `owlia-gpt-5-5-judge` | Stored remote-server id for semantic judging. |
| `judge_model` | `--judge-model` | `MELIX_JUDGE_MODEL` | `gpt-5.5` | Remote model id used by the judge server. |
| `bench_suite` | `--bench-suite` | `MELIX_BENCH_SUITE` | `smoke` | Benchmark suite id. |
| `bench_context_length` | `--bench-context-length` | `MELIX_BENCH_CONTEXT_LENGTH` | `1024` | Benchmark prompt context length. |
| `bench_generation_length` | `--bench-generation-length` | `MELIX_BENCH_GENERATION_LENGTH` | `128` | Benchmark generation length. |
| `bench_batch_size` | `--bench-batch-size` | `MELIX_BENCH_BATCH_SIZE` | `1` | Benchmark batch size. |
| `bench_repeats` | `--bench-repeats` | `MELIX_BENCH_REPEATS` | `1` | Benchmark repeat count. |
| `bench_sample_size` | `--bench-sample-size` | `MELIX_BENCH_SAMPLE_SIZE` | `1` | Benchmark sample limit. |
| `bench_batch_factor` | `--bench-batch-factor` | `MELIX_BENCH_BATCH_FACTOR` | `1` | Benchmark dataset batch factor. |
| `eval_suite` | `--eval-suite` | `MELIX_EVAL_SUITE` | `event_extraction` | Evaluation suite id. |
| `eval_dataset_id` | `--eval-dataset-id` | `MELIX_EVAL_DATASET_ID` | `top200.event-extraction.top20.v1` | Managed evaluation dataset id. |
| `eval_scoring_mode` | `--eval-scoring-mode` | `MELIX_EVAL_SCORING_MODE` | `event_extraction_weighted_f1` | Evaluation scoring mode. |
| `eval_sample_size` | `--eval-sample-size` | `MELIX_EVAL_SAMPLE_SIZE` | `20` | Evaluation sample limit. |
| `eval_batch_factor` | `--eval-batch-factor` | `MELIX_EVAL_BATCH_FACTOR` | `1` | Evaluation batch factor. |
| `continue_on_failure` | `--continue-on-failure` | `MELIX_CONTINUE_ON_FAILURE` | `true` | Whether one model failure allows the batch to continue. |
| `restart_stack_per_model` | `--restart-stack-per-model` | `MELIX_RESTART_STACK_PER_MODEL` | `true` | Whether execution restarts the local stack between models. |
| `preflight` | `--preflight` | `MELIX_BATCH_PREFLIGHT` | `false` | Whether dry-run planning also writes a health gate report and blocks on missing long-run prerequisites. |

Batch configs must reference stored credentials by id, not embed raw credential
values. For semantic judging, `judge_remote_server_id` identifies a remote
server already configured through the Melix remote-server store; any API key
remains in the local secret store and never appears in the batch config,
terminal summary, effective configuration artifact, or manifest. Config keys
that look like raw secret fields, such as `*_api_key`, `*_token`, `*_secret`, or
`*_password`, must be rejected before planning begins.

### Manifest Planning

Batch-run planning must write `manifest.jsonl` in both the temporary run
directory and the operator output directory. Each selected model receives one
JSONL record with `schema_version: melix.batch.manifest_entry.v1`.

The initial dry-run manifest entry status is `planned`. Per-step statuses start
as `pending` for:

- `preflight`
- `runtime_prepare`
- `model_unload`
- `hub_check`
- `benchmark`
- `evaluation`
- `exports`
- `artifact_copy`

Each manifest entry includes top-level `failure_category` and `recoverability`
fields, and every step carries the same fields for execution-time attribution.
The failure categories are stable strings:

- `worker_connectivity`
- `runtime_unavailable`
- `metal_oom`
- `target_resolution`
- `model_load`
- `judge_failure`
- `artifact_export`
- `unknown_failure`

Recoverability values are:

- `retry_same_model`
- `clean_restart_and_retry`
- `operator_action_required`
- `not_recoverable`
- `unknown`

Non-dry-run execution may update model status to:

- `running`
- `succeeded`
- `failed`
- `partial_success`
- `recovered`

`partial_success` is reserved for models where one product line, such as
benchmarking or evaluation, completed and produced auditable artifacts while
another product line failed.

Execution updates each step with:

- `status`
- `job_id`
- `stdout_path`
- `stderr_path`
- `artifact_path`
- `started_at`
- `finished_at`
- `duration_seconds`
- `failure_category`
- `recoverability`
- `message`

Top-level execution rows also persist `benchmark_job_id`,
`evaluation_job_id`, exported CSV/JSONL paths, copied raw artifact paths,
duration, metric fields parsed from command JSON, and failure attribution.

### Execution Pipeline

For each selected model, non-dry-run batch execution must stage model-specific
temporary and output directories, then run these stages in order:

- `preflight`
- `runtime_prepare`
- `model_unload`
- `hub_check`
- `benchmark`
- `evaluation`
- `exports`
- `artifact_copy`

`benchmark` dispatches `melix bench run --repo-id <repo_id> ... --json` and
then `melix bench export-csv --job-id <job_id> --output <model>/exports/benchmark.csv`.
`evaluation` dispatches `melix eval run --repo-id <repo_id> ... --json` with
the configured semantic judge and then exports summary CSV, samples CSV, and
samples JSONL under the model exports directory.

The batch runner records subprocess stdout and stderr for every dispatched
command under `<model>/commands/`. Command receipts must also persist the child
process exit code. Exit code, not stderr text alone, decides subprocess success:
stderr from an exit-zero command is preserved as evidence and noted in the step
message, while non-zero exits fail the step using stderr, or stdout when stderr
is empty, as the diagnostic message. Missing job ids are treated as execution
failures because downstream export commands would otherwise be ambiguous.

### Status And Resume

`melix batch status` must resolve a run by explicit temporary root, explicit
output root, or run id. It reads `manifest.jsonl`, summarizes totals, and emits
either compact text or JSON.

`melix batch resume` must load an existing manifest and recovered effective
configuration, rebuild the model list from manifest rows when `--models` is not
provided, and execute only incomplete work by default. `--eval-only` skips
benchmark stages and reruns missing or failed evaluation/export work. `--dry-run`
for resume prints the planned model rows without dispatching commands.

Resume planning must align existing manifest records back to selected models by
`index`, `repo_id`, and `source_line`, preserving duplicate rows independently
instead of collapsing them by display index or repo id. When resume rebuilds a
model list from manifest rows, it must preserve source-line positions by
inserting blank spacer lines before records whose original source line was
greater than the current recovered line count.

Resume must preserve the original run id, temporary root, output root, judge,
benchmark, and evaluation settings when they are available in
`effective-config.json`.

### Summary Artifacts

After each non-dry-run batch completion or resume, Melix must write these
operator-visible artifacts to `output_root`:

- `manifest.jsonl`
- `effective-config.json`
- `RUN_SUMMARY.md`
- `run-summary.json`
- `run-summary.csv`
- `index.html`

The summary artifacts include totals, per-model status, benchmark and
evaluation job ids, duration, failure category, recoverability, and links or
paths for exported artifacts.

### Runtime Health Preflight

`melix batch run --dry-run --preflight` must validate prerequisites before an
operator starts an expensive sweep. It writes `preflight-report.json` to both
the temporary run directory and the operator output directory, and it fails
before execution if any check is `blocked`.

The preflight report uses `schema_version: melix.batch.preflight_report.v1` and
records:

- the isolated `MELIX_HOME`, runtime dir, service instance, HTTP port, repo root,
  and CLI artifact path
- judge remote-server id and judge model
- selected model ids
- check rows for CLI artifact, runtime directories, output directories, disk
  capacity, cache state, model repo-id shape, dataset materialization, and
  judge config
- each check row includes `category` and `metadata` fields so later status,
  resume, and report renderers can group failures without parsing prose

Judge config preflight confirms that the remote-server record and API key exist
in the isolated `MELIX_HOME`. Provider reachability remains an execution-time
failure category recorded by the per-model evaluation stage.

Runtime config preflight blocks bare default stack settings. Batch runs must use
a named instance, an isolated `MELIX_HOME`, an isolated runtime directory, and a
non-default HTTP port. The gate treats both the current bare default port
`12436` and the legacy bare default port `11434` as unsafe for long batch mode.

Stack-product preflight verifies the Melix CLI artifact, the control-plane
executable, and the Python worker entrypoint before a long run starts.

### Isolation Policy

The effective config includes `isolation_policy` with
`schema_version: melix.batch.isolation_policy.v1`. The policy defaults to:

- best-effort unload of the previous model before a model starts
- best-effort unload after a model finishes
- `restart_stack_per_model: true`
- force a clean stack after runtime failure categories such as worker
  connectivity loss or Metal OOM
- cleanup failures preserve per-model artifacts

### Terminal Summary

Dry-run terminal output must show:

- `run_id`
- selected and total model counts
- subset controls when present
- temporary and output roots
- judge server and judge model
- preflight status and report path when `--preflight` is used
- failure-continuation and per-model stack restart policy
- effective configuration and manifest paths
- one compact `PLAN` line per selected model

Non-dry-run terminal output must show:

- run id and selected model counts
- per-model `START`, stage start/success, semantic judge heartbeat, and `DONE`
  lines
- failure category and message when a stage fails
- final status totals
- manifest and summary artifact paths

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
- paired comparison evidence for `eval compare`
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

## Shared Dataset Selection

Both product lines may run against an operator-selected managed dataset using a
dataset reference in the form `repo_id[@revision]`.

When a managed dataset reference is provided:

- `repo_id` is the Hugging Face dataset repository id
- `repo_id` must not contain `@`; malformed references are rejected before
  reaching worker-side Hugging Face calls
- `revision` defaults to `main`
- for evaluation commands that also pass `--hf-dataset-revision`, the explicit
  revision option takes precedence over the revision embedded in `dataset_ref`
- the worker should prefer a local Hugging Face cache snapshot under
  `~/.cache/huggingface/hub/datasets--*`
- if no local snapshot is available, the evaluation and benchmark materializers
  may fall back to the Hugging Face Dataset Viewer API
- persisted run parameters must include `dataset_ref`, `hf_dataset_path`, and
  `hf_dataset_revision`

Dataset references select the dataset source only. Existing field mapping,
split, config, sample-size, and suite semantics still determine how rows become
benchmark prompts or evaluation samples.

## Source-Anchored Dataset Construction

Source-anchored multimodal and agentic datasets must still materialize into
Melix-owned training or evaluation packages before training, `eval`, or
`compare` execution. The construction process is governed by
`docs/plans/2026-05-22-source-anchored-data-construction.md`.

That plan defines the required construction path for source inventory,
image/entity selection, fuzzy rewrites, multi-hop question assembly, and package
materialization. DataDesigner-backed generation may persist optional
`source_construction` metadata in training and final-result evaluation package
manifests and sample rows. Later leakage-validation slices should consume that
metadata and write validation summaries to the existing package contracts rather
than creating a separate runtime dataset format.

When source-anchored validation is applied, package manifests must include a
`source_leakage_validation` object with a publishable summary of the checks that
ran. The summary reports validator names, status, checked row and segment
counts, split source-id counts when a training validation split exists, and the
minimum raw-value length used for lexical leakage matching. It must not persist
raw excluded field values, prompt text, observations, source spans, or other
payload text that could reintroduce answer leakage into release artifacts.

When source-quality metrics are available, package manifests must also include a
`source_quality_metrics` object that reports tool necessity, multi-hop depth,
evidence coverage, answer ambiguity, source diversity, and transformation
diversity from sanitized `source_construction` metadata. These metrics are
descriptive evidence only; sample accept/reject reports remain a separate
selection artifact.

## Benchmark Fixture Sources

Benchmark suites may also materialize from repository-owned fixture packages
under `services/mlx-worker-python/fixtures/benchmark/`. These sources are used
when CI or local agentic benchmark runs need deterministic prompts and tool
fixture context without remote dataset or network search dependencies.

The checked-in benchmark fixture package shape is:

- `manifest.json`
  - `schema_version: melix.benchmark_fixture_package.v1`
  - `fixture_package_id`
  - `suite_id`
  - `task_kind`
  - `version`
  - `sample_count`
  - `split`
- `samples.jsonl`
  - one JSON object per benchmark row
  - for agentic `text-generation` suites, each row must include `prompt`
  - tool-use rows may include `tool_calls` and `tool_fixture_context`

Fixture-backed benchmark materialization must write the standard benchmark
materialization package with:

- `source_kind: melix_benchmark_fixture`
- `dataset_uri: melix-fixture://benchmark/<fixture_package_id>`
- `fixture_package_id`

The default fixture-backed agentic benchmark suites are:

- `agentic_image`: deterministic image-inspection and image-search tool path
- `agentic_search`: deterministic text-search tool path
- `agentic_visit`: deterministic page-visit tool path

These suites use `task_kind: text-generation` because they benchmark agentic
tool-use prompts and preserve the shared `tool_calls` plus
`tool_fixture_context` row contract. The tool names and observation semantics
remain governed by `docs/unified-agentic-tool-runtime-contract.md`; benchmark
fixtures must not introduce benchmark-only tool names.

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

Direct Hugging Face target resolution must prefer the explicit Hub
`pipeline_tag` when it is present. Some valid MLX repositories omit
`pipeline_tag`; Melix may infer the task kind from stronger repository metadata
such as MLX/Qwen text-generation signals, sibling tokenizer and weight files,
or explicit modality tags. A missing `pipeline_tag` alone is not an unsupported
task-family signal.

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
- zero or more request-level phase rows
- task-aware summary metrics
- exportable CSV rows

### Performance Probe Fields

Benchmark context-sweep and batch-sweep rows must preserve these additive diagnostic probe fields
when the runner can observe them:

- `dataset_materialize_ms`
- `prompt_render_ms`
- `warmup_ms`
- `prefill_ms`
- `decode_ms`
- `tokens_in`
- `tokens_out`
- `first_token_index`
- `cache_hit`
- `runtime_kind`
- `error_stage`
- `speculative_acceptance_rate`
- `speculative_rollback_rate`
- `speculative_accepted_tokens`
- `speculative_rejected_tokens`
- `speculative_fallback_count`
- `speculative_num_draft_tokens`
- `speculative_draft_model_configured`
- `speculative_draft_propose_ms`
- `speculative_target_verify_ms`
- `dflash_enabled`
- `dflash_block_size`
- `dflash_rollback_count`
- `dflash_target_hidden_layers`

The fields are phase-localization aids. Missing or zero values do not invalidate older persisted
artifacts, but new runners should populate them so operators can distinguish dataset
materialization, prompt rendering, prefill, decode, runtime-cache, speculative decode, DFlash, and
failure-stage regressions.

Swift export decoders may default missing additive numeric and boolean probes to `0` or `false`
when reading legacy artifacts. Consumers must treat those defaults as compatibility sentinels
unless the producing runner version is known to emit the probe field; they are not proof that the
phase completed in zero milliseconds or that a boolean probe was explicitly observed as false.

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

### Request-Level Phase Rows

Each completed `bench run` may persist request-level phase rows in
`bench-request-rows.jsonl` and `bench-request-rows.csv`. New text benchmark
runners should emit at least one `final_answer` phase row per measured request.
Agentic fixture-backed suites must additionally emit one `tool_turn` phase row
per executed tool call before the final-answer row.

Each request-level phase row must include:

- `schema_version`
- `job_id`
- `model_id`
- `task_kind`
- `source_repo`
- `suite`
- `context_length`
- `generation_length`
- `batch_size`
- `repeat_index`
- `request_index`
- `phase`
- `phase_index`
- `status`
- `error_code`
- `error_stage`
- `duration_ms`
- `ttft_ms`
- `request_latency_ms`
- `prefill_tokens_per_second`
- `decode_tokens_per_second`
- `peak_memory_bytes`
- `dataset_materialize_ms`
- `prompt_render_ms`
- `warmup_ms`
- `prefill_ms`
- `decode_ms`
- `tokens_in`
- `tokens_out`
- `first_token_index`
- `cache_hit`
- `runtime_kind`
- `tool_call_id`
- `tool_name`
- `tool_arguments_json`
- `tool_observation_json`
- `tool_call_count`
- `tool_latency_ms`
- `observation_bytes`
- `fatal_rate`
- `turn_count`
- `compare_target_kind`
- `base_model_id`
- `adapter_manifest_path`
- `adapter_set_hash`
- `adapter_activation_mode`
- `created_at_unix_ms`

`phase` is `tool_turn` for deterministic local tool execution and
`final_answer` for the model generation phase. Non-agentic benchmark requests
emit only `final_answer`. For `tool_turn` rows, `tool_arguments_json` and
`tool_observation_json` are compact JSON object strings derived from the shared
agentic tool runtime. For `final_answer`, tool-specific fields default to empty
strings while aggregate tool-turn fields may summarize the request.

For base-vs-adapter benchmark comparison, request rows must make the comparison
target identity explicit without requiring readers to inspect runtime state.
`compare_target_kind` is `base` for ordinary model rows and `adapter` when the
row was produced by an adapter-backed LoRA target. `base_model_id` identifies
the source model used as the comparison baseline. Adapter rows must include the
adapter package manifest path, adapter set hash, and activation mode when those
values are available from benchmark job parameters. Base rows must clear
adapter-only fields during persistence and export collection so stale adapter
metadata from older request rows cannot be interpreted as LoRA lineage.

Reports derive base-vs-adapter agentic benchmark deltas from these request rows
without requiring live runtime or registry state. For each export side, the
report groups base rows by suite, context length, generation length, batch size,
phase, and `base_model_id`, then matches adapter rows by the same group plus
adapter manifest path, adapter set hash, and activation mode. Matched rows
produce `comparison.agentic_adapter_deltas`; unmatched adapter or base-only rows
are omitted rather than rendered as partial comparisons.

Agentic adapter deltas cover:

- `tool_call_count`
- `tool_latency_ms`
- `observation_bytes`
- `fatal_rate`
- `turn_count`
- `request_latency_ms`
- `ttft_ms`

Each delta row must preserve side, suite, shape, phase, base model id, adapter
identity, metric name, base value, adapter value, delta, delta percent,
direction, gate policy, status, and result. Markdown, terminal, and
`comparison_deltas.csv` report outputs must render the same structured rows with
`kind=agentic_adapter` in the CSV.

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

Persisted matrix job records must include the additive `parameters` map. Live-runtime runs should
copy runtime evidence into that map using the `runtime_*` keys listed in the report contract so the
PR report can expose target/runtime mismatches alongside numeric deltas.

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
- `cell_wall_ms`
- `completed_count`
- `failed_count`
- `ttft_p50_ms`
- `ttft_p95_ms`
- `request_latency_p50_ms`
- `request_latency_p95_ms`
- `tool_call_count`
- `tool_latency_ms`
- `observation_bytes`
- `fatal_rate`
- `turn_count`
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
- `dataset_materialize_ms`
- `prompt_render_ms`
- `warmup_ms`
- `prefill_ms`
- `decode_ms`
- `tokens_in`
- `tokens_out`
- `first_token_index`
- `cache_hit`
- `runtime_kind`
- `error_stage`
- `speculative_acceptance_rate`
- `speculative_rollback_rate`
- `speculative_accepted_tokens`
- `speculative_rejected_tokens`
- `speculative_fallback_count`
- `speculative_num_draft_tokens`
- `speculative_draft_model_configured`
- `speculative_draft_propose_ms`
- `speculative_target_verify_ms`
- `dflash_enabled`
- `dflash_block_size`
- `dflash_rollback_count`
- `dflash_target_hidden_layers`
- `tool_call_count`
- `tool_latency_ms`
- `observation_bytes`
- `fatal_rate`
- `turn_count`
- `created_at_unix_ms`

The agentic tool-turn fields are derived from the shared agentic tool runtime
records governed by `docs/unified-agentic-tool-runtime-contract.md`.
`tool_call_count`, `observation_bytes`, and `turn_count` are request counts or
byte totals. `tool_latency_ms` is total tool adapter time for the row.
Request-level `fatal_rate` is `1.0` when any tool observation for that request
has timeout or failed status and `0.0` otherwise. Matrix summary `fatal_rate`
is the fraction of requests in the cell with a fatal tool outcome.

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
- `source`
- `field_mapping`
- `profile`
- `eval_prompt`
- `eval_prompt_file`
- `eval_prompt_id`
- `eval_prompt_revision`

`eval_prompt` and `eval_prompt_file` are one-off system prompts for a single
`eval run`. They are mutually exclusive with each other and with the frozen
registry selector `eval_prompt_id`. A one-off prompt applies to every requested
evaluation suite in the run. It is prepended after Melix's suite instruction and
before any sample-provided system text; it must not replace the sample input
text. The worker records prompt identity, revision, title, and content hash
parameters using the ad hoc identity `ad-hoc.evaluation.prompt` /
`ad-hoc`, but must not persist prompt content in job parameters.

Executable-code suites add one enforcement rule:

- `humaneval` and `mbpp` must reject execution unless `code_exec_policy = sandboxed`

Evaluation dataset overrides may also provide:

- `dataset_id`
- `dataset_root`

### Comparison Mode

`eval compare` reuses the same evaluation job family while adding one base target and one or more
comparison targets.

The canonical comparison extension fields are:

- `compare_mode: base_vs_targets`
- `compare_target_model_ids: string[]`
- `compare_target_adapter_manifest_paths: string[]`

`compare_target_model_ids` names registered catalog targets that are already
loadable by the local runtime. `compare_target_adapter_manifest_paths` names
LoRA adapter package manifests with schema `melix.lora_adapter_package.v1`.
During local compare execution, Melix resolves each adapter manifest into an
ephemeral adapter-backed target using the manifest's source model, weights path,
and adapter set hash. Those ephemeral targets are unloaded after compare
execution finishes.

A comparison request is valid when it has exactly one base target, expressed
through `model_id` or `hf_repo_id`, and at least one comparison target across
`compare_target_model_ids` and `compare_target_adapter_manifest_paths`.

Comparison runs must persist through the same shared history and export bundle
as `eval run`. The persisted compare bundle must also expose one
machine-readable release evidence view:

- `dataset_lineage` records the materialized dataset root and normalized dataset
  source fields used for the paired base and target samples.
- `target_lineage` records each comparison target's materialization kind. For
  adapter targets, it includes the adapter manifest path, adapter weights path,
  adapter set hash, and source model id used to derive the ephemeral target.
- `statistical_verdicts` records each target's verdict, effect threshold, delta
  accuracy, statistical evidence, and release-gate summary.

`evaluation-compare-job.json`, `evaluation-compare-summary.json`, and
`run-record.json` must preserve enough of this lineage/verdict data for a
release reviewer to verify which adapter was compared, which dataset slice was
used, and why the statistical verdict was emitted without joining against
process logs.

### Release Gate Verdict Policy

Release-gate policies select compare suites through the keys under
`evaluation_compare`. For every selected suite, the release gate must find
persisted paired compare evidence and apply that suite's verdict policy.

Supported verdict policies are:

- `required_verdict_mode: exact` with `required_verdict`: the compare verdict
  must equal the configured verdict. Target-domain LoRA suites use this mode to
  require a statistically supported `improvement`.
- `required_verdict_mode: non_regression`: the compare verdict must not be
  `regression`. Guard suites use this mode to block statistically supported
  regressions while accepting `improvement`, `inconclusive`, or tie-like neutral
  verdicts.

When `required_verdict_mode` is omitted, `exact` is the compatibility default
whenever `required_verdict` is present.

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
- `source_kind: string`
- `source_path: string`
- `source_dataset_path: string`
- `source_dataset_name: string`
- `source_dataset_revision: string`
- `source_split: string`
- `field_mapping_system_path: string`
- `field_mapping_input_text_path: string`
- `field_mapping_target_path: string`
- `field_mapping_sample_id_path: string`
- `profile_type: string`
- `result_kind: string`
- `extraction_mode: string`
- `profile_threshold: number`
- `output_schema_json: string`
- `ignored_paths: string[]`
- `compare_target_model_ids: string[]`
- `compare_target_adapter_manifest_paths: string[]`

### Current Control Semantics

The current Melix runtime enforces these shipped control semantics:

- `few_shot` consumes demonstration rows from the same materialized evaluation package used for
  scoring.
- `seed` deterministically orders the package rows before Melix slices out `few_shot` demos and
  scored samples.
- demonstration rows are never counted inside `sample_size`.
- compare jobs must reuse the same seeded row order and the same few-shot plan across the base and
  target runs.
- `seed` is also threaded into worker `SamplingConfig.seed` for runtimes that honor sampling seeds.
- `scoring_mode` selects a real scorer implementation, not only a stored label:
  - `multiple_choice_accuracy`
  - `exact_match`
  - `pass_at_1`
- unsupported scorer or policy combinations must fail with an explicit invalid-argument style
  error.

The current supported scorer matrix is:

- `mmlu`, `arc_challenge`, `hellaswag`, `winogrande`, `truthfulqa_mc`:
  `multiple_choice_accuracy` or `exact_match`
- `imagenette`, `gsm8k`: `exact_match`
- `humaneval`, `mbpp`: `pass_at_1`

The current shipped `code_exec_policy` rules are:

- non-code suites default to `disabled`
- `humaneval` and `mbpp` default to `sandboxed`
- non-code suites must reject execution-enabled policies such as `sandboxed`
- code suites must reject disabled policies because executable scoring is the evidence path
- `sandboxed` means the worker executes candidate Python inside a dedicated temporary directory
  under macOS `sandbox-exec`, with writes confined to that directory, network denied, and stdout
  plus stderr bounded before the result is accepted
- workers that cannot enforce `sandboxed` execution must reject the evaluation run before code is
  executed

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

The checked-in development fixtures for executable-code evaluation are:

- `humaneval.dev.v1`
- `mbpp.dev.v1`

These packages live under `services/mlx-worker-python/fixtures/evaluation/` and are the canonical
development-time execution datasets for Melix v1 code evaluation.

The checked-in development fixtures for agentic multimodal evaluation are:

- `agentic-multihop-qa.dev.v1`
- `agentic-visual-retrieval-qa.dev.v1`
- `agentic-document-lookup-qa.dev.v1`

These packages also live under `services/mlx-worker-python/fixtures/evaluation/`. They are small
repository-owned development packages that cover image-grounded multi-hop QA, visual retrieval QA,
and document lookup QA. Each package keeps package-local media or document assets and deterministic
`tool_calls` plus `tool_fixture_context` data that replay through the unified agentic tool runtime.

The agentic multimodal fixtures are contract and regression fixtures, not benchmark scorecards. They
do not change final-result scorer dispatch, judge policy, or production evaluation latency. Later
agentic-evaluation milestones may add richer trajectory capture, paired report artifacts, and
judge-backed acceptance metrics on top of these repository-owned packages.

#### Agentic Multimodal Sample Field Contract

Agentic multimodal evaluation samples use
`melix.agentic_multimodal_sample_fields.v1` as the stable field contract. The
contract applies to repository-owned development fixtures and any later
materialized package that opts into the same agentic suite family.

Each sample row must define these required fields:

- `question`: non-empty string shown to the model; it must match `input.text`.
- `media_refs`: non-empty array of package-local media or document references.
- `expected_answer`: non-empty string containing the normalized final answer; it must match `target`.
- `evidence_ids`: non-empty array of stable evidence identifiers.
- `allowed_tools`: non-empty array of tool names available to the sample.

Each `media_refs` entry must be an object with:

- `id`: stable sample-local media identifier.
- `kind`: media class such as `image` or `document`.
- `uri`: package-relative path resolved against the fixture package root.

`media_refs[].uri` must not be absolute and must not use a network URL. The
runtime may use `input.image_uri` or `input.document_uri` as a convenience for
model input shaping, but `media_refs` is the authoritative package-local asset
inventory for the sample.

`evidence_ids` must reference evidence available from the sample itself or its
deterministic tool fixture context. Valid sources include:

- `media_refs[].id`
- media fragments such as `<media_ref>#<region>` used by deterministic image tools
- `id` fields inside `tool_fixture_context`
- explicit `evidence_ids` arrays inside `tool_fixture_context`

`allowed_tools` must be a subset of the package manifest's `allowed_tools`.
Every `tool_calls[].name` value must be listed in sample-level
`allowed_tools`; sample-level tools may be narrower than the package manifest
to keep one sample's callable surface explicit.

The sample field contract is intentionally separate from final-result scoring.
It proves that the sample is self-describing, that all local media and evidence
claims are traceable, and that deterministic tool replay has a bounded tool
surface. It does not add a new scorer, judge policy, or production execution
probe.

#### Agentic Evaluation Trajectory Execution

When an evaluation sample provides `tool_calls`, `EvaluationCore` must replay
those calls through the unified deterministic agentic tool runtime before live
model inference. The replayed assistant tool-call turns and tool observation
turns are appended to the sample's evaluation prompt before final generation, so
the scored model answer is produced with the executed trajectory in context.

The persisted sample evidence remains the authoritative execution record:
`agentic_tool_registry`, `agentic_tool_calls`, `agentic_tool_observations`, and
`agentic_tool_metrics`. Measurement points for this path are the existing
`agentic_tool.*` metrics, including call count, completed/timeout/failed status
counts, observation emitted bytes, observation count, and tool latency.

Each persisted evaluation sample row must also be self-contained for trajectory
audit. When the source sample provides raw `tool_calls`, the row must preserve
those raw calls alongside executed `agentic_tool_observations`, the scored
`final_answer`, the `parse_status` that produced that answer, and the
`failure_stage` classification. These fields make the sample JSONL sufficient
for report bundles and follow-up alignment analysis without reconstructing
state from prompts or terminal logs.

#### Agentic Evaluation Judge Audit Artifacts

Agentic multimodal evaluation suites also write judge audit artifacts so later
judge-backed scoring can replay the exact answer-equivalence boundary without
depending on terminal output or hidden process state. A suite opts into this
contract by setting `agentic_suite_family` in its evaluation dataset manifest.

The initial artifact slice is audit-only. It does not call a remote judge,
change scorer dispatch, change exact-match scores, or add production latency.
Melix still computes `typed_score` with the configured final-result scorer, and
the judge artifacts record the prompt and sample boundary that a later
judge-backed scorer can consume.

Each persisted agentic evaluation job must include these parameters:

- `agentic_judge_prompt_snapshot`: path to
  `agentic-judge-prompt-snapshots.jsonl`.
- `agentic_judge_audit`: path to `agentic-judge-audit.jsonl`.
- `agentic_judge_prompt_version`: stable prompt version string.
- `agentic_judge_prompt_hash`: content hash for the judge system prompt.

`agentic-judge-prompt-snapshots.jsonl` is one JSON object per selected sample.
Each row must include:

- `schema_version: melix.agentic_judge_prompt_snapshot.v1`
- `job_id`, `suite_id`, `dataset_id`, and `sample_id`
- `agentic_suite_family`
- `judge_prompt_version`
- `judge_prompt_hash`
- `judge_role`
- `rubric`
- `messages`
- `allowed_tools`
- `evidence_ids`
- `media_refs`
- `tool_calls`
- `agentic_tool_observation_count`

`messages` must contain the judge system instruction and a user payload with the
question, expected answer, model final answer, parse status, scoring mode,
evidence ids, media refs, raw tool calls, and executed tool observations. It
must not include API keys, remote base URLs, or provider credentials.

The judge user payload is the no-leak boundary for later judge-backed scoring.
It may contain only these fields: `question`, `expected_answer`,
`final_answer`, `parse_status`, `scoring_mode`, `evidence_ids`, `media_refs`,
`tool_calls`, and `tool_observations`. The `expected_answer` field is the only
gold-answer input allowed in judge context beyond the rubric. Sample-derived
media refs, raw tool calls, and executed tool observations must be rejected
before prompt snapshot persistence when any nested key names hidden gold,
answer keys, reference solutions, provider credentials, API keys, tokens,
passwords, or remote base URLs. Literal answer text remains allowed as a value
inside `expected_answer`, `final_answer`, and executed observations because
those fields are part of the explicit scoring boundary.

`agentic-judge-audit.jsonl` is one JSON object per selected sample. Each row
must include:

- `schema_version: melix.agentic_judge_audit.v1`
- `job_id`, `suite_id`, `dataset_id`, and `sample_id`
- `agentic_suite_family`
- `judge_prompt_version`
- `judge_prompt_hash`
- `judge_status`
- `judge_source`
- `typed_score`
- `scoring_mode`
- `final_answer`
- `parse_status`
- `failure_stage`
- `validation_status`
- `extraction_status`
- `tool_call_count`
- `agentic_tool_observation_count`
- `evidence_ids`
- `error_code`
- `failure_reason`

For the initial audit-only slice, `judge_status` is `pending` and
`judge_source` is `not_called`; the row records the deterministic final-result
score as the baseline exact-match outcome. Later judge-backed scoring may append
or replace judge decision fields, but it must preserve the prompt version and
hash link between audit rows and prompt snapshot rows.

### Evaluation Dataset Contract

Melix evaluation executes only against repository-owned evaluation dataset packages.

Every execution package must provide:

- `manifest.json`
- `samples.jsonl`

External datasets, including Hugging Face datasets, may be reused as source inputs, but they must
be materialized into a Melix evaluation dataset package before execution.

The authoritative runtime contract is the materialized evaluation package rather than any external
source schema.

For code-execution suites (`humaneval`, `mbpp`), each scored sample must also provide:

- `test_code`

These optional fields are supported for code suites:

- `entry_point`
- `code_timeout_seconds`

### Final-Result Evaluation Profile

Melix now executes `final_result` evaluation packages and can materialize structured sources through
`eval run` before worker execution.

Current request-driven source materialization supports:

- local CSV files
- local JSONL files
- Hugging Face datasets

Current request-driven materialization also requires explicit field mapping for custom sources and
supports profile overrides for typed extraction, validation, and scoring.

Current limitation:

- compare entry points still target existing suites or packages; ad hoc custom dataset sources are
  currently exposed on `eval run`

Each structured evaluation dataset package declares a single evaluation profile in `manifest.json`
with these core fields:

- `profile_type: final_result`
- `result_kind: json | text`
- `extraction_mode: strict_full_response | heuristic_final`
- `scoring_mode`
- `threshold`

`final_result` sample rows use these fields:

- `system`
- `input`
- `target`

The Melix execution contract remains the materialized evaluation package rather than any external
dataset schema.

#### Final-Result Principles

The `final_result` profile is the runtime abstraction for structured and non-structured LoRA
evaluation.

Its contract is intentionally narrow:

- only the extracted final result is scored
- `raw_response` is retained for debugging, not correctness scoring
- CoT or other wrapper text may appear in `raw_response`, but it is not itself evaluation evidence
- v1 covers ground-truth evaluation only; no-target or format-only evaluation is deferred
- task names such as `extraction`, `relationship`, and `summarization` remain suite metadata rather
  than scorer dispatch keys

#### Result Kinds

The current v1 `result_kind` set is:

- `json`
- `text`

For `result_kind: json`:

- `target` must be valid JSON with root type `object` or `array`
- `output_schema` defines the accepted JSON root type and schema rules
- schema validation is required before scoring begins
- object roots support field-level comparison in v1
- array roots use conservative comparison in v1 rather than broad task-specific logic

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

For `result_kind: json`, the shared extractor ladder is:

- prefer the last contentful fenced `json` block
- otherwise use the last contentful fenced block whose contents parse as JSON
- otherwise use the last terminal balanced JSON suffix
- if multiple same-priority candidates remain, record `ambiguous_extraction`

For `result_kind: text`, the shared extractor ladder is:

- prefer the last terminal `Final answer:` or `Answer:` span
- otherwise use the last contentful fenced text block
- otherwise use the last terminal non-empty line or paragraph
- if multiple same-priority candidates remain, record `ambiguous_extraction`

The current PR direction of describing extraction as "last valid JSON value" is not stable enough
for the long-term contract because it is JSON-specific and under-specifies ambiguity handling.

#### Scoring Model

The current execution pipeline is:

- capture `raw_response`
- extract `extracted_result`
- validate the extracted result for its declared `result_kind`
- normalize as required by `scoring_mode`
- score only the extracted result against `target`

In the `final_result` path, correctness is computed from `extracted_result` rather than the
full response text.

Some repository fixtures may still originate from legacy `prompt` and `expected` content, but the
runtime contract and exported evaluation evidence are normalized around `final_result`.

### Evaluation Summary Outputs

Each completed suite result must include:

- `job_id`
- `task_kind`
- `source_repo`
- `model_id`
- `suite_id`
- `dataset_id`
- `primary_score_name`
- `primary_score_value`
- `sample_size`
- `extraction_success_count`
- `validation_success_count`
- `scored_sample_count`
- `failure_count`
- `effect_threshold`
- `verdict`
- `bootstrap_lower_bound`
- `bootstrap_upper_bound`
- `analytical_lower_bound`
- `analytical_upper_bound`
- `duration_seconds`
- `created_at_unix_ms`

Standard `eval run` rows may omit the statistical comparison fields or leave them empty.

`eval compare` rows must populate them.

### Statistical Evidence

When the result comes from `eval compare`, the persisted comparison summary must also retain:

- `delta_accuracy`
- `base_accuracy`
- `target_accuracy`
- `win_count`
- `loss_count`
- `tie_count`
- `regression_count`
- `effect_threshold`
- `verdict`
- `statistical_evidence`
- `release_gate_summary`

`statistical_evidence` must include both `bootstrap` and `analytical` interval families. Each
family must record:

- `method`
- `confidence_level`
- `lower_bound`
- `upper_bound`
- `crosses_zero`

The shipped comparison verdict set is:

- `improvement`
- `regression`
- `inconclusive`

Melix must classify comparison verdicts with the same `CI + threshold` rule everywhere:

- emit `improvement` only when observed delta clears the positive effect threshold and both
  interval families stay above zero
- emit `regression` only when observed delta clears the negative effect threshold and both
  interval families stay below zero
- emit `inconclusive` otherwise

Human-readable compare reports must separate target summaries into:

- quality improvements
- regressions
- inconclusive results

Each report group must include target model id, verdict, delta accuracy,
effect threshold, regression count, and interval detail. Empty groups must be
explicitly rendered so release reviewers can distinguish "no results in this
group" from a missing report section.

### Category Breakdown

When the suite supports category or subject scoring, the result must also include:

- `category_scores: { [category_name]: number }`

When the suite supports category-aware comparison evidence, `eval compare` must also emit a
`category_breakdown` keyed by category label.

Absence of category support must be represented by omission rather than an empty map.

### Sample-Level Outputs

Each sample-level row must include:

- `job_id`
- `suite_id`
- `id`
- `target`
- `extracted_result`
- `final_answer`
- `input_text`
- `raw_response`
- `typed_score`
- `time_s`
- `extraction_status`
- `parse_status`
- `validation_status`
- `failure_reason`
- `input_modalities`
- `media_references`
- `code_language`
- `code_entry_point`
- `code_compile_status`
- `code_runtime_status`
- `code_timeout_status`
- `code_test_status`
- `code_tests_passed`
- `code_tests_total`
- `code_failure_detail`
- `category_label`
- `subject_label`
- `sample_render_ms`
- `inference_ms`
- `extraction_ms`
- `validation_ms`
- `scoring_ms`
- `raw_response_chars`
- `extracted_result_chars`
- `failure_stage`

Summary rows report extraction and validation counts. Sample rows report the extracted result,
typed score, and failure reason for operator-visible debugging.

Evaluation probe fields localize failures by evaluation phase: sample rendering, inference,
extraction, validation, scoring, and final failure classification. Character-count fields are
debugging aids for response truncation and extraction behavior. Run-evidence probe timelines must
represent large evaluation sample sets with aggregate phase summaries plus a bounded representative
sample set for slowest top-N, failed, skipped, and fallback samples; they must not expand every
persisted sample into full per-sample probes.

For executable-code suites, these additional fields are required evidence rather than optional
metadata. Melix v1 must preserve compile, runtime, timeout, and test outcomes through persistence,
export, and compare workflows.

### Evaluation Export Formats

`eval export-summary-csv` must emit one row per suite result with these columns:

- `job_id`
- `task_kind`
- `source_repo`
- `model_id`
- `suite_id`
- `dataset_id`
- `primary_score_name`
- `primary_score_value`
- `sample_size`
- `extraction_success_count`
- `validation_success_count`
- `scored_sample_count`
- `failure_count`
- `effect_threshold`
- `verdict`
- `bootstrap_lower_bound`
- `bootstrap_upper_bound`
- `analytical_lower_bound`
- `analytical_upper_bound`
- `duration_seconds`
- `created_at_unix_ms`

`eval export-samples-csv` must emit one row per evaluated sample with these columns:

- `job_id`
- `suite_id`
- `id`
- `target`
- `extracted_result`
- `final_answer`
- `input_text`
- `raw_response`
- `typed_score`
- `time_s`
- `extraction_status`
- `parse_status`
- `validation_status`
- `failure_reason`
- `input_modalities`
- `media_references`
- `code_language`
- `code_entry_point`
- `code_compile_status`
- `code_runtime_status`
- `code_timeout_status`
- `code_test_status`
- `code_tests_passed`
- `code_tests_total`
- `code_failure_detail`
- `category_label`
- `subject_label`
- `sample_render_ms`
- `inference_ms`
- `extraction_ms`
- `validation_ms`
- `scoring_ms`
- `raw_response_chars`
- `extracted_result_chars`
- `failure_stage`

`eval export-samples-jsonl` must emit the same sample-level fields as line-delimited JSON objects.

## Benchmark And Evaluation Report Contract

Melix provides a local and CI report over exported benchmark/evaluation bundles.

The report command is:

```bash
python scripts/benchmark_evaluation_report.py \
  --baseline <baseline-export-or-directory> \
  --candidate <candidate-export-or-directory> \
  --format terminal|markdown|json
```

The report accepts either a bundle file or a directory containing `benchmark-evaluation-export.json`
or `export-bundle.json`.

The report aggregates summary metrics plus additive benchmark request probes, matrix request probes,
evaluation sample timing probes, failure-stage counts, run-evidence aggregate probes, and runtime
metadata rows from persisted job parameters. Representative sample-detail probes are diagnostic
context and must not be counted as additional aggregate duration or failure metrics.

Report semantics:

- lower is better for latency, duration, memory, byte, queue-wait, warmup, prefill, decode,
  failure-count, failed-count, speculative rollback, rejected-token, speculative fallback, draft
  proposal, target verification, and DFlash rollback metrics
- lower is better for matched-context agentic tool-turn cost and reliability metrics:
  tool-call count, completed-tool count, observation count, turn count, tool latency,
  observation bytes, fatal rate, timeout count, and failed-tool count
- higher is better for throughput, success-rate, accuracy, typed-score, pass-rate, and win-count
  metrics, plus speculative acceptance and accepted-token metrics
- runtime metadata from job parameters is rendered as metadata rows; matching values are `ok`, and
  differing non-numeric values are `not_comparable`
- advisory status values are `ok`, `warning`, `missing`, and `not_comparable`
- regression warnings do not fail CI; malformed report inputs are the only non-zero report-script
  exit path

The PR workflow must run base SHA and PR head on the same macOS runner with isolated `MELIX_HOME`,
runtime directories, model-ops roots, and HTTP ports. The default CI report runtime is
deterministic so reports remain comparable on hosted runners without a runner-local model checkout
or Swift MLX metallib cache. In deterministic mode the workflow also pins `MELIX_DEV_TEXT_MODEL_PATH`
to a slash-free logical path so legacy base-SHA control planes do not classify the seed dev model as
a remote repository that requires live-model evidence. The workflow prebuilds Swift runtime products
before startup so worker readiness waits measure process readiness rather than cold compilation time.
It uploads base, head, and report artifacts, then updates one sticky pull-request comment identified by:

```html
<!-- melix-benchmark-evaluation-report -->
```

`eval compare export-summary-csv` must emit one row per base-versus-target summary with these
columns:

- `job_id`
- `base_model_id`
- `target_model_id`
- `suite_id`
- `dataset_id`
- `sample_size`
- `win_count`
- `loss_count`
- `tie_count`
- `regression_count`
- `base_accuracy`
- `target_accuracy`
- `delta_accuracy`
- `duration_seconds`

`eval compare export-samples-csv` must emit one row per comparison sample with these columns:

- `job_id`
- `suite_id`
- `dataset_id`
- `sample_id`
- `target_model_id`
- `question`
- `expected`
- `base_predicted`
- `target_predicted`
- `base_raw_response`
- `target_raw_response`
- `base_correct`
- `target_correct`
- `outcome`
- `regression`
- `base_time_s`
- `target_time_s`
- `base_parse_status`
- `target_parse_status`
- `code_language`
- `code_entry_point`
- `base_code_compile_status`
- `target_code_compile_status`
- `base_code_runtime_status`
- `target_code_runtime_status`
- `base_code_timeout_status`
- `target_code_timeout_status`
- `base_code_test_status`
- `target_code_test_status`
- `base_code_tests_passed`
- `target_code_tests_passed`
- `base_code_tests_total`
- `target_code_tests_total`
- `base_code_failure_detail`
- `target_code_failure_detail`

`eval compare export-samples-jsonl` must emit the same comparison-sample fields as line-delimited
JSON objects.

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
When a diagnostics surface opens with no persisted benchmark, matrix, or
evaluation history, any automatic history refresh must follow the currently
selected or preferred diagnostics surface. It must not reset an evaluation or
compare entry point back to the performance surface.

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
- compare verdict, threshold, and confidence-interval detail when statistical evidence is present
- compare report groups for quality improvements, regressions, and inconclusive results
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
- `melix eval compare`
- `melix eval list`
- `melix eval export-summary-csv`
- `melix eval export-samples-csv`
- `melix eval export-samples-jsonl`
- `melix eval compare export-summary-csv`
- `melix eval compare export-samples-csv`
- `melix eval compare export-samples-jsonl`

All commands must support `--json`.

Human-readable output is required by default.

## Forward Compatibility

Future benchmark work may extend `bench matrix` to additional task kinds or add release-gate integration, but it must preserve:

- the distinct `bench run` and `bench matrix` command surfaces
- the distinct standard and matrix export schemas
- explicit `benchmark_mode` persistence in shared run history
