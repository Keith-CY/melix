# Model Registry Config Payload Reuse Plan

## Goal

Elide redundant model-registry `config.json` payload reload calls by reusing the already loaded payload when `WorkerModelCatalog` converts a discovered plain-local or Hugging Face cache model directory into a `ModelSpec`.

## Constraints

- Host verification is Linux-only.
- Keep the slice Python-only and behavior-preserving.
- Preserve the compatibility path where `_raw_model_spec(...)` can still load `config.json` itself for direct callers that do not already have a parsed payload.

## Touched Files

- `services/mlx-worker-python/worker/model_registry/catalog.py`
- `services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Task

1. Thread an optional `config_payload` argument into `_raw_model_spec(...)` and pass the already loaded payload from the plain-local and Hugging Face cache discovery paths.
2. Add focused regression tests for plain-local reuse, Hugging Face cache reuse, the `_raw_model_spec(...)` fallback path, and malformed `config.json` MLX-signal compatibility when the parsed payload is unusable.
3. Update the existing model-registry PR-scoped performance probe so its focused test/coverage commands include the new regression tests and its probe output records config-payload load calls alongside elapsed time.

## Probe Definition

- Probe ID: `model-registry-plain-local-manifest-stat-elision`
- Local measurement path: run the registered probe command from `infra/perf/pr_scoped_probes.json` and compare concrete metrics on `origin/main` vs the branch.
- Key metric goal: reduce `config_load_calls_mean` while preserving discovered model count.
- Secondary metric goal: do not regress `elapsed_ms_mean` materially.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_records_plain_local_weight_presence_during_single_scandir_pass \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_plain_local_tree_scan_and_config_payload \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_hf_cache_config_payload \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_raw_model_spec_loads_config_payload_when_not_supplied \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_empty_supplied_payload \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_skips_config_text_fallback_for_nonempty_payload_without_mlx_signal \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_unserializable_nonempty_payload \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_plain_local_manifest_after_tree_scan \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_load_json_dict_file_reads_json_bytes_without_text_decode \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_records_plain_local_weight_presence_during_single_scandir_pass \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_plain_local_tree_scan_and_config_payload \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_hf_cache_config_payload \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_raw_model_spec_loads_config_payload_when_not_supplied \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_empty_supplied_payload \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_skips_config_text_fallback_for_nonempty_payload_without_mlx_signal \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_unserializable_nonempty_payload \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_plain_local_manifest_after_tree_scan \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_load_json_dict_file_reads_json_bytes_without_text_decode \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics \
  && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json \
  && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
     services/mlx-worker-python/worker/model_registry/catalog.py \
     services/mlx-worker-python/tests/test_model_registry_catalog.py \
     services/mlx-worker-python/tests/test_pr_scoped_performance.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python bash -lc '<registered model-registry probe command>'

git diff --check
```