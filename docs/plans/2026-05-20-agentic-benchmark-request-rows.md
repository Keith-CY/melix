# Agentic Benchmark Request Row Persistence Plan

## Goal

Persist request-level benchmark rows for every agentic tool turn and final
answer phase in fixture-backed agentic benchmark runs.

## Scope

- Covers issue #710 under the OpenSearch-VL agentic benchmark metrics
  direction.
- Adds additive ordinary `bench run` request-row artifacts:
  `bench-request-rows.jsonl` and `bench-request-rows.csv`.
- Captures one `tool_turn` phase row per executed tool call plus one
  `final_answer` phase row for each benchmark request.
- Adds request-row probes to benchmark/evaluation comparison reports under
  phase-specific `bench.request.<suite>...<phase>` labels.
- Keeps matrix request rows unchanged; matrix already has
  `bench-matrix-requests.jsonl` and summary aggregation from the previous
  milestone.

## Architecture

Ordinary serving benchmark context and batch rows are aggregate-oriented: they
preserve request metrics and nested agentic evidence, but they do not expose a
stable phase row for each tool turn. This slice adds a separate request-row
artifact so downstream reports can inspect tool-turn failures and final-answer
cost without parsing nested debug payloads.

Each persisted request row uses schema version
`melix.serving_benchmark_request_row.v1` and includes:

- benchmark identity: `job_id`, `model_id`, `task_kind`, `source_repo`,
  `suite`, `context_length`, `generation_length`, `batch_size`,
  `repeat_index`, `request_index`
- phase identity: `phase`, `phase_index`, `status`, `error_code`,
  `error_stage`
- timing and token probes: `duration_ms`, `dataset_materialize_ms`,
  `prompt_render_ms`, `warmup_ms`, `prefill_ms`, `decode_ms`, `tokens_in`,
  `tokens_out`, `first_token_index`, `cache_hit`, `runtime_kind`
- agentic fields: `tool_call_id`, `tool_name`, `tool_arguments_json`,
  `tool_observation_json`, `tool_call_count`, `tool_latency_ms`,
  `observation_bytes`, `fatal_rate`, `turn_count`

For non-agentic benchmark requests, Melix writes only the `final_answer` row.
For agentic fixture-backed requests, Melix writes one `tool_turn` row per
normalized tool call followed by `final_answer`. The full nested
`agentic_tool_*` evidence remains on existing context and batch rows.

## Performance Probes And Metrics

- Measurement points:
  - `tool_turn` row count and status distribution
  - `final_answer` row timing and token probes
  - request-row artifact write path and export collection
  - comparison report metrics for request-row timing, throughput, and agentic
    aggregate probes
- Success metrics:
  - every text benchmark request persists exactly one `final_answer` row.
  - agentic requests persist one additional `tool_turn` row per executed tool.
  - request rows are collected into benchmark export bundles and CSV output.
  - request-row report probes are grouped by phase so tool-turn and final-answer
    measurements are not co-aggregated.
  - existing context, batch, matrix, and report semantics remain backward
    compatible.

## Implementation Plan

1. Update `docs/benchmark-evaluation-contract.md` with the ordinary benchmark
   request-row artifact contract.
2. Add schema helpers and canonical CSV columns for serving benchmark request
   rows.
3. Extend `BenchmarkStore.persist_serving_benchmark` and benchmark export
   collection to write/read `bench-request-rows.jsonl` and CSV.
4. Extend text benchmark measurement to build phase rows from each measured
   sample and associated agentic tool run.
5. Add focused tests for schema serialization, store/export collection, and
   `bench run` fixture-backed request-row persistence.
6. Extend benchmark/evaluation comparison reports to collect phase-specific
   request-row probes.

## Verification

- `git diff --check`
- Focused Python tests:
  - `services/mlx-worker-python/tests/test_benchmark_schemas.py`
  - `services/mlx-worker-python/tests/test_benchmark_store.py`
  - `services/mlx-worker-python/tests/test_benchmark_export.py`
  - `services/mlx-worker-python/tests/test_maintenance_service.py`
- Changed-scope coverage for modified Python implementation files.

## Known Gaps

- This slice does not add new report UI tables for the phase rows; the rows are
  persisted and exported for follow-on analysis.
- Live external search or visit providers remain out of scope. The request
  rows are produced from deterministic local fixture tool execution.
