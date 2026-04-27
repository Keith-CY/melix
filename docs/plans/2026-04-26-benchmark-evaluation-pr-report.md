# Benchmark Evaluation PR Report Plan

## Goal

Add phase-level performance and accuracy probes to benchmark, matrix, and evaluation artifacts, then
surface base-versus-head deltas in both local terminal output and a sticky pull-request comment.

## Scope

- Extend persisted benchmark rows with dataset materialization, prompt rendering, warmup, prefill,
  decode, token, cache, runtime, and error-stage probes.
- Extend benchmark matrix summary rows with cell wall time, completed and failed counts, and p50/p95
  latency probes.
- Extend evaluation sample rows with render, inference, extraction, validation, scoring, response
  size, extracted-result size, and failure-stage probes.
- Add a shared report builder that reads export bundles and renders terminal, Markdown, or JSON
  output.
- Add a pull-request workflow that runs base SHA and PR head on the same macOS runner and updates one
  sticky PR comment.

## Architecture

The Python worker remains the execution truth for benchmark and evaluation probes. Existing schemas
are extended additively so old artifacts continue to decode with zero or empty default values.

The report builder consumes export bundles instead of live runtime state. This keeps local debugging
and CI rendering identical:

- `scripts/benchmark_evaluation_report.py` is the operator entry point.
- `worker.productization.benchmark_evaluation_report` owns loading, comparison, status, and
  rendering logic.
- `.github/workflows/bench-eval-report.yml` runs both revisions, writes export bundles, renders the
  report, uploads artifacts, and updates the sticky comment.
- The PR workflow defaults to deterministic text execution so hosted macOS reports do not depend on
  a runner-local model checkout or Swift MLX metallib cache. Real Swift MLX report runs still require
  an explicit matching `MELIX_SWIFT_MLX_METALLIB_PATH` and model path.
- In deterministic CI mode the workflow pins `MELIX_DEV_TEXT_MODEL_PATH` to a slash-free logical
  path so legacy base-SHA control planes do not require live-model evidence for the seed dev model.
- The workflow prebuilds Swift runtime products before startup so readiness waits are not consumed
  by cold Swift compilation on hosted runners.

## Probe Semantics

Benchmark probe stages:

- dataset/materialization: `dataset_materialize_ms`
- prompt/rendering: `prompt_render_ms`
- warmup: `warmup_ms`
- prefill: `prefill_ms`
- decode: `decode_ms`
- runtime attribution: `tokens_in`, `tokens_out`, `first_token_index`, `cache_hit`, `runtime_kind`
- failures: `error_stage`
- speculative decode: `speculative_acceptance_rate`, `speculative_rollback_rate`,
  `speculative_accepted_tokens`, `speculative_rejected_tokens`, `speculative_fallback_count`,
  `speculative_num_draft_tokens`, `speculative_draft_model_configured`,
  `speculative_draft_propose_ms`, `speculative_target_verify_ms`
- DFlash: `dflash_enabled`, `dflash_block_size`, `dflash_rollback_count`,
  `dflash_target_hidden_layers`
- job runtime metadata: `runtime_live_model`, `runtime_model_handle`, `runtime_kind`,
  `runtime_name`, `runtime_model_id`, `runtime_model_path`, `runtime_source_kind`,
  `runtime_source_repo`

Evaluation probe stages:

- rendering: `sample_render_ms`
- inference: `inference_ms`
- extraction: `extraction_ms`
- validation: `validation_ms`
- scoring: `scoring_ms`
- response sizing: `raw_response_chars`, `extracted_result_chars`
- failures: `failure_stage`

## Report Semantics

The comparison is advisory. Direction-aware regression warnings are visible in the report but do not
fail CI.

- Lower is better for latency, duration, memory, byte, queue-wait, warmup, prefill, decode,
  failure-count, failed-count, speculative rollback, rejected-token, speculative fallback, draft
  proposal, target verification, and DFlash rollback metrics.
- Higher is better for throughput, success-rate, accuracy, typed-score, pass-rate, and win-count
  metrics, plus speculative acceptance and accepted-token metrics.
- Runtime metadata is rendered as metadata rows so base/head target mismatches are visible without
  failing the report.
- Evaluation sample probes are aggregated by suite so rendering, inference, extraction, validation,
  scoring, response-size, and failure-stage shifts are visible next to score deltas.
- Status values are `ok`, `warning`, `missing`, and `not_comparable`.
- The report script exits non-zero only for malformed inputs.

## Verification

- Python schema, export, report, and renderer tests cover additive field preservation and
  direction-aware deltas.
- Swift `BenchmarkExportBundleTests` cover additive decode and CSV rendering for matrix and
  evaluation probe fields.
- Workflow validation uses `actionlint`.
- Full handoff should include `make py-test`, targeted Swift export tests, `make swift-test`, and
  `make integration-test` when integration plumbing is affected.

## Metrics Report

Changed-scope metrics are produced by the new report builder itself. For local debugging, operators
can generate the same evidence with:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
  uv run --project services/mlx-worker-python \
  python scripts/benchmark_evaluation_report.py \
    --baseline <baseline-export-or-directory> \
    --candidate <candidate-export-or-directory> \
    --format terminal \
    --output-dir <report-output-directory>
```
