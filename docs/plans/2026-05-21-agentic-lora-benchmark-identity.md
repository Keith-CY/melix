# Agentic LoRA Benchmark Identity Plan

## Goal

Implement issue #712 by adding benchmark export request rows that link adapter
identity to request-level and tool-turn performance.

## Scope

- Covers the first executable unit under issue #711, Milestone 3 of the
  OpenSearch-VL agentic benchmark metrics direction.
- Adds additive base/adapter identity fields to serving benchmark request rows
  and their CSV export.
- Automatically annotates collected request rows from `bench-job.json`
  parameters when persisted rows predate the new fields.
- Keeps PR/report delta rendering out of scope for issue #713.

## Architecture

Request rows are already the canonical phase-level benchmark artifact for
tool-turn and final-answer performance. This slice extends that artifact with
comparison identity:

- `compare_target_kind`: `base` for ordinary model rows, `adapter` for
  adapter-backed LoRA rows.
- `base_model_id`: the source model being compared against.
- `adapter_manifest_path`, `adapter_set_hash`, and `adapter_activation_mode`:
  adapter lineage needed to group rows by adapter package and runtime mode.

Rows built directly by benchmark schema helpers accept the fields explicitly.
Rows collected from disk are enriched from serving benchmark job parameters.
This keeps the export bundle self-contained and avoids requiring a live
registry during export.

## Performance Probes And Metrics

- Measurement points:
  - request-row JSONL/CSV write path
  - export collection enrichment from one job payload plus request rows
  - tool-turn fields already present on enriched rows:
    `tool_call_count`, `tool_latency_ms`, `observation_bytes`, `fatal_rate`,
    and `turn_count`
- Success metrics:
  - adapter-backed rows expose adapter lineage without parsing nested runtime
    metadata.
  - base rows expose `compare_target_kind: base` and stable `base_model_id`.
  - CSV exports include the new identity columns.
  - existing request-row exports remain backward compatible when no adapter
    metadata exists.

## Implementation Plan

1. Add failing schema and export tests for adapter identity on request rows.
2. Extend `ServingBenchmarkRequestRow` and
   `build_serving_benchmark_request_row` with additive identity fields.
3. Add the new fields to canonical benchmark request CSV columns.
4. Enrich collected benchmark request rows from matching job parameters during
   export collection.
5. Update `docs/benchmark-evaluation-contract.md`.
6. Run focused tests, changed-scope coverage, and `git diff --check`.

## Verification

- `git diff --check`
- Focused pytest:
  - `services/mlx-worker-python/tests/test_benchmark_schemas.py`
  - `services/mlx-worker-python/tests/test_benchmark_export.py`
  - `services/mlx-worker-python/tests/test_benchmark_store.py`
- Changed-scope coverage for modified Python files.

## Known Gaps

- This slice does not render base-vs-adapter delta tables in PR or benchmark
  reports. That remains issue #713.
