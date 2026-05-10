# Issue 353 Serving Diagnostics Bundles Plan

## Goal

Close the serving diagnostics artifact slice for issue #353 by adding a stable,
product-owned artifact contract for opted-in serving debug sessions and
baseline-vs-accelerated evidence comparisons.

## Scope

- Add a Python worker productization module that writes stable serving
  diagnostics bundle directories.
- Record manifest, effective config, request summary, and request event JSONL
  artifacts with prefill, throughput, cache, finish, and memory fields.
- Add a baseline-vs-accelerated evidence artifact that rejects ambiguous
  comparisons across different prompt protocols or non-deterministic sampling.
- Surface the same throughput counters in lightweight loaded-model status
  payloads with type-stable float defaults.
- Document lightweight diagnostics versus performance-claim evidence usage.

## Files

- Add `services/mlx-worker-python/worker/productization/serving_diagnostics.py`
- Add `services/mlx-worker-python/tests/test_serving_diagnostics.py`
- Add `docs/runbooks/serving-diagnostics-evidence.md`
- Update `packages/protocol/schema/worker/v1/runtime.proto`
- Update generated protocol artifacts
- Update `services/mlx-worker-python/worker/registry.py`
- Update `services/mlx-worker-python/worker/engine/engine_core.py`
- Update `services/mlx-worker-python/tests/test_generate_stream.py`
- Update `services/mlx-worker-python/tests/test_runtime_service.py`
- Update `docs/README.md`

## Artifact Layout

Serving diagnostics bundles are written under:

```text
serving-diagnostics/<bundle_id>/
  manifest.json
  effective-config.json
  request-summary.json
  events.jsonl
```

Baseline comparison artifacts are written as:

```text
serving-diagnostics/<comparison_id>/baseline-vs-accelerated.json
```

## Performance Probes And Metrics

The changed path is an artifact-writing path. Metrics are recorded inside the
artifacts and covered by tests rather than a hot-path runtime benchmark:

- `prefill_ms`
- `prefill_tokens_per_second`
- `prompt_tps`
- `generation_tps`
- `cache_hit_tokens`
- `cache_miss_tokens`
- `cache_restored_tokens`
- `cache_computed_tokens`
- `effective_temperature`
- `sampler_is_greedy`
- `acceleration_admitted`
- `fallback_reason`
- `tier_stability_status`

## Tasks

1. Add failing artifact-layout tests for manifest, effective config, request
   summary, event JSONL, prefill fields, and float throughput defaults.
2. Add failing validation tests for invalid prefill chunk size overrides.
3. Add failing baseline-vs-accelerated comparison tests for same-protocol,
   deterministic sampling, methodology receipts, and prefill phase rows.
4. Implement the diagnostics artifact writer and comparison writer.
5. Add loaded-model status fields for `prompt_tps` and `generation_tps` with
   float `0.0` defaults and runtime-event updates.
6. Document operator guidance and add the runbook to the docs index.
7. Run focused tests, changed-line coverage, and PR evidence validation before
   opening the PR.

## Acceptance Criteria

- A debug serving diagnostics bundle can be reproduced from stable JSON files.
- Every request summary preserves first-class prefill, throughput, cache, finish,
  and memory fields with type-stable defaults.
- Invalid prefill chunk size overrides fail before artifact/session creation.
- Baseline-vs-accelerated evidence rejects mismatched prompt protocols and
  non-greedy sampler settings.
- Baseline-vs-accelerated evidence rejects missing or non-finite phase metrics
  instead of synthesizing zero-duration values.
- Baseline-vs-accelerated evidence records effective sampler settings,
  acceleration admission, fallback reason, tier stability, and a prefill phase
  comparison row.
- `ListLoadedModels` returns `prompt_tps` and `generation_tps` for every loaded
  model, preserves float `0.0` defaults before counters are available, and
  updates those fields from served runtime events.
- Documentation explains debugging-only bundles versus claim-supporting
  comparison artifacts.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_runtime_service.py::test_list_loaded_models_reports_float_throughput_defaults services/mlx-worker-python/tests/test_runtime_service.py::test_loaded_model_throughput_ignores_missing_invalid_and_unknown_updates services/mlx-worker-python/tests/test_generate_stream.py::test_generate_stream_updates_loaded_model_status_throughput_fields services/mlx-worker-python/tests/test_generate_stream.py::test_generate_stream_keeps_loaded_model_status_defaults_without_throughput services/mlx-worker-python/tests/test_generate_stream.py::test_decode_updates_loaded_model_status_throughput_fields
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage run --source=worker.productization.serving_diagnostics,worker.registry,worker.engine.engine_core -m pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py services/mlx-worker-python/tests/test_runtime_service.py::test_list_loaded_models_reports_float_throughput_defaults services/mlx-worker-python/tests/test_runtime_service.py::test_loaded_model_throughput_ignores_missing_invalid_and_unknown_updates services/mlx-worker-python/tests/test_generate_stream.py::test_generate_stream_updates_loaded_model_status_throughput_fields services/mlx-worker-python/tests/test_generate_stream.py::test_generate_stream_keeps_loaded_model_status_defaults_without_throughput services/mlx-worker-python/tests/test_generate_stream.py::test_decode_updates_loaded_model_status_throughput_fields
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /private/tmp/issue353_coverage.json
python3 scripts/python_changed_line_coverage.py --coverage-json /private/tmp/issue353_coverage.json --diff-from origin/main services/mlx-worker-python/worker/productization/serving_diagnostics.py services/mlx-worker-python/worker/registry.py services/mlx-worker-python/worker/engine/engine_core.py services/mlx-worker-python/tests/test_serving_diagnostics.py services/mlx-worker-python/tests/test_runtime_service.py services/mlx-worker-python/tests/test_generate_stream.py
make py-test
```
