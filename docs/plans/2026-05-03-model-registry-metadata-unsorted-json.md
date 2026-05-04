# Plan: model registry metadata unsorted JSON fast path

## Goal

Remove unnecessary `sort_keys=True` work from the model-registry MLX-signal metadata path so plain-local and Hugging Face config payload checks avoid redundant key sorting while preserving detection behavior.

## Scope

- `services/mlx-worker-python/worker/model_registry/catalog.py`
- `services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-only constraint

This is a Python-only slice and will be verified locally on Linux. No macOS-only runtime behavior is required for local validation.

## Intended change

- Keep the current JSON-string-based MLX-signal detection contract.
- Stop requesting sorted JSON keys in:
  - `_metadata_payload_has_mlx_signal(...)`
  - the `config_payload` fast path inside `_has_mlx_signal(...)`
- Add focused regression tests that prove these call sites no longer ask `json.dumps(..., sort_keys=True)`.
- Update the existing `model-registry-plain-local-manifest-stat-elision` scoped probe test/coverage commands so changed-scope CI covers the new focused tests.

## Performance probe

Reuse the existing PR-scoped probe:

- Probe ID: `model-registry-plain-local-manifest-stat-elision`
- Probe path: `infra/perf/pr_scoped_probes.json`

Local measurement path before commit:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python scripts/pr_scoped_performance_run.py --probe-id model-registry-plain-local-manifest-stat-elision --output /tmp/model-registry-probe.json
```

## Success metrics

- No behavior change in MLX-signal detection for the targeted payload shapes.
- Changed executable scope coverage >= 95%.
- Local scoped probe completes successfully and reports concrete metrics.
- `git diff --check` passes.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_records_plain_local_weight_presence_during_single_scandir_pass \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_plain_local_tree_scan_and_config_payload \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_missing_plain_local_generation_config_after_tree_scan \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_imports_plain_local_generation_config_when_seen_during_tree_scan \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_hf_cache_config_payload \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_raw_model_spec_loads_config_payload_when_not_supplied \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_empty_supplied_payload \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_skips_config_text_fallback_for_nonempty_payload_without_mlx_signal \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_unserializable_nonempty_payload \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_metadata_payload_has_mlx_signal_does_not_request_sorted_json \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_config_payload_fast_path_does_not_request_sorted_json \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_plain_local_manifest_after_tree_scan \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_skips_invalid_depth_manifests_without_parsing \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_load_json_dict_file_reads_json_bytes_without_text_decode \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same test selection>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python scripts/pr_scoped_performance_run.py --probe-id model-registry-plain-local-manifest-stat-elision --output /tmp/model-registry-probe.json
git diff --check
```