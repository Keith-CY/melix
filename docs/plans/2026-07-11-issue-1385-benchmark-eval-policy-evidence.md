# Issue 1385 Benchmark And Evaluation Policy Evidence Slice

## Goal

Propagate text effective-policy evidence into benchmark and evaluation export
rows so benchmark/eval artifacts can prove which sampling and template policy
was effective for each measured request or scored sample.

## End-State Architecture

Effective text policy is request-local run evidence. The control plane already
emits a deterministic `melix.text_effective_policy_receipt.v1` receipt before
worker dispatch. Benchmark and evaluation artifacts must preserve the same
policy surface at row granularity:

- benchmark request rows carry the effective sampling/template policy used for
  the measured request;
- benchmark matrix request rows carry the same fields for each matrix cell
  request;
- evaluation sample rows carry the policy evidence for each scored sample;
- JSONL artifacts preserve typed values, and CSV exports expose stable flat
  columns for report and spreadsheet consumers.

## Scope

- Add shared Python export field definitions for flattened effective-policy
  evidence.
- Let benchmark request rows, benchmark matrix request rows, and evaluation
  sample rows carry policy evidence when the caller provides a text
  effective-policy receipt.
- Extend persisted JSONL and generated CSV headers/rows for benchmark request,
  benchmark matrix request, and evaluation sample artifacts.
- Extend the Swift benchmark export bundle decoder and CSV/JSONL re-export path
  so desktop/control-plane surfaces do not drop the new fields.
- Update `docs/benchmark-evaluation-contract.md` with the row-level policy
  evidence contract.

## Out Of Scope

- Production source-verified catalog entries.
- New benchmark/evaluation operator controls for strict recommended sampling.
- Desktop visual inspection controls beyond preserving the export data.
- Changing benchmark or evaluation execution scheduling.

## Policy Evidence Columns

Rows use a stable flat column set derived from
`melix.text_effective_policy_receipt.v1`:

- `effective_policy_schema`
- `effective_config_hash`
- `sampling_temperature`
- `sampling_temperature_source`
- `sampling_top_p`
- `sampling_top_p_source`
- `sampling_max_tokens`
- `sampling_max_tokens_source`
- `sampling_policy_lookup_status`
- `sampling_policy_canonical_model`
- `sampling_policy_matched_alias`
- `sampling_policy_source_url`
- `sampling_request_override_applied`
- `recommended_sampling_required`
- `sampling_seed`
- `sampling_seed_source`
- `chat_template_source`
- `chat_template_effective_kwargs_hash`
- `chat_template_request_override_applied`
- `chat_template_forced_override_applied`
- `policy_reasoning_mode`
- `policy_reasoning_source`

Missing policy evidence serializes as empty strings, numeric zero values, or
`false` booleans according to the field type.

## TDD Steps

1. Add failing Python tests proving benchmark request rows persist flattened
   policy fields in JSONL and CSV.
2. Add failing Python tests proving benchmark matrix request CSV exports and
   evaluation sample JSONL/CSV exports keep the same fields.
3. Add failing Swift bundle tests proving decoded benchmark matrix request rows
   and evaluation sample rows preserve the new policy fields through CSV and
   JSONL re-export.
4. Implement a shared Python effective-policy evidence helper and wire the
   benchmark/evaluation schema builders and CSV headers.
5. Implement matching Swift decode/encode/CSV fields.
6. Update the benchmark/evaluation contract.
7. Run focused Python and Swift tests, changed-line coverage, and scoped
   performance report before PR.

## Metrics And Verification

- Focused Python tests:

  ```bash
  PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q \
    services/mlx-worker-python/tests/test_benchmark_schemas.py \
    services/mlx-worker-python/tests/test_benchmark_store.py \
    services/mlx-worker-python/tests/test_benchmark_export.py \
    services/mlx-worker-python/tests/test_evaluation_schemas.py \
    services/mlx-worker-python/tests/test_evaluation_store.py
  ```

- Focused Swift tests:

  ```bash
  xcrun swift test --package-path services/control-plane-swift --filter BenchmarkExportBundleTests
  ```

- Changed-line coverage for touched Python and Swift scopes must be at least
  95 percent.
- Scoped performance report must be `ok` with zero in-scope regressions. This
  slice changes export row serialization, so registered benchmark/evaluation
  export probes may be selected.
- The `evaluation-store-samples-csv-streaming` elapsed gate allows a 20 percent
  or 350 ms delta for this slice because the canonical sample row schema
  intentionally widens every persisted sample by the effective-policy evidence
  fields. The probe still gates focused behavior coverage and peak memory at the
  standard 5 percent threshold, and the implementation keeps JSONL/CSV writing
  streaming rather than materializing one large payload.
