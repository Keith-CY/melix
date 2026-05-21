# Agentic LoRA Benchmark Delta Rendering Plan

## Goal

Implement issue #713 by rendering base-vs-adapter agentic benchmark deltas in
the benchmark/evaluation report and PR sticky comment.

## Scope

- Covers the second executable unit under issue #711, Milestone 3 of the
  OpenSearch-VL agentic benchmark metrics direction.
- Uses request-row identity fields added by #712:
  `compare_target_kind`, `base_model_id`, `adapter_manifest_path`,
  `adapter_set_hash`, and `adapter_activation_mode`.
- Adds report-structured base-vs-adapter delta rows for agentic request metrics.
- Renders those rows in markdown, terminal output, and comparison delta CSV.
- Does not change benchmark execution, adapter runtime activation, or request
  row persistence.

## Architecture

Serving benchmark request rows are the canonical phase-level source for tool-use
cost. The report builder should derive in-bundle base-vs-adapter deltas from
those rows before comparing two separate export bundles. This keeps LoRA
comparison available for both local report generation and PR sticky comments
without requiring a live registry or runtime state.

The report will aggregate request rows by:

- suite
- context length
- generation length
- batch size
- phase
- base model id
- adapter identity

For each adapter group, it will match base rows with the same suite, shape,
phase, and base model id. It will compute direction-aware deltas for:

- `tool_call_count`
- `tool_latency_ms`
- `observation_bytes`
- `fatal_rate`
- `turn_count`
- `request_latency_ms`
- `ttft_ms`

Rows are stored under `comparison.agentic_adapter_deltas` and included in
`comparison_deltas.csv` with `kind=agentic_adapter`. Markdown and terminal
rendering use the same structured rows so artifact and PR views stay aligned.

## Performance Probes And Metrics

- Measurement points:
  - report build request-row grouping
  - markdown rendering of adapter deltas
  - comparison delta CSV output
- Success metrics:
  - changed-scope coverage for modified Python files is at least 95 percent.
  - PR-scoped performance report remains `Status: ok`.
  - adapter deltas are absent when request rows lack a matched base/adapter
    pair, avoiding misleading partial comparisons.

## Implementation Plan

1. Add failing report tests for one matched base/adapter pair and one unmatched
   adapter row.
2. Add a focused aggregator that computes base-vs-adapter request-row deltas.
3. Attach `agentic_adapter_deltas` to the report comparison section.
4. Render the rows in markdown and terminal output.
5. Include the rows in `comparison_deltas.csv`.
6. Update `docs/benchmark-evaluation-contract.md`.
7. Run focused tests, changed-scope coverage, `git diff --check`, and
   PR-scoped performance.

## Verification

- `git diff --check`
- Focused pytest:
  - `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`
- Changed-scope coverage for:
  - `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`
  - `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`
- PR-scoped performance for `benchmark-evaluation-report-running-aggregates`
  if selected by changed files.

## Known Gaps

- This slice renders deltas for persisted request-row metrics only. It does not
  synthesize quality-score deltas from evaluation compare outputs.
- Rows without a matched base and adapter are intentionally omitted from delta
  rendering; missing-pair diagnostics can be added later if operators need
  explicit coverage accounting.
