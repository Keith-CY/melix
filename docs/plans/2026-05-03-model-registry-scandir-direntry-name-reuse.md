# Model Registry Scandir DirEntry Name Reuse

## Scope

This performance slice keeps model registry discovery behavior unchanged while narrowing the plain-local registry scan hot path in `worker/model_registry/catalog.py`.

The scan loop already uses `os.scandir()` and `DirEntry` descriptor checks. This slice reuses each entry name once per loop iteration and hoists the pruned directory-name collection out of the loop so large registry roots avoid repeated `DirEntry.name` lookups and per-directory set allocation.

The 2026-05-31 follow-up slice keeps the same registered probe and narrows the remaining child-directory scheduling cost by sorting the collected child names in place before extending the DFS stack, avoiding the extra list allocated by `sorted(...)` while preserving deterministic traversal order.

## Registered probe

The affected path is covered by the existing PR-scoped probe `model-registry-plain-local-manifest-stat-elision` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- `test_command` for focused model registry behavior tests and PR-scoped probe selection tests.
- `coverage_command` for changed-scope coverage across `catalog.py`, focused catalog tests, and PR-scoped performance tests.
- `probe_command` that builds an 800-model synthetic registry and reports elapsed scan time plus stat/parse/load counters.

This slice also changes the registered probe command from `python` to `python3` so local and CI probe execution follows the repository instruction to avoid the ambiguous `python` executable.

## Verification plan

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_records_plain_local_weight_presence_during_single_scandir_pass services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_plain_local_tree_scan_and_config_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_missing_plain_local_generation_config_after_tree_scan services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_imports_plain_local_generation_config_when_seen_during_tree_scan services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_hf_cache_config_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_raw_model_spec_loads_config_payload_when_not_supplied services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_empty_supplied_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_skips_config_text_fallback_for_nonempty_payload_without_mlx_signal services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_unserializable_nonempty_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_plain_local_manifest_after_tree_scan services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_skips_invalid_depth_manifests_without_parsing services/mlx-worker-python/tests/test_model_registry_catalog.py::test_load_json_dict_file_reads_json_bytes_without_text_decode services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_records_plain_local_weight_presence_during_single_scandir_pass services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_plain_local_tree_scan_and_config_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_missing_plain_local_generation_config_after_tree_scan services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_imports_plain_local_generation_config_when_seen_during_tree_scan services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_hf_cache_config_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_raw_model_spec_loads_config_payload_when_not_supplied services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_empty_supplied_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_skips_config_text_fallback_for_nonempty_payload_without_mlx_signal services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_unserializable_nonempty_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_plain_local_manifest_after_tree_scan services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_skips_invalid_depth_manifests_without_parsing services/mlx-worker-python/tests/test_model_registry_catalog.py::test_load_json_dict_file_reads_json_bytes_without_text_decode services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
# registered probe command from infra/perf/pr_scoped_probes.json
```

## Success criteria

- Focused behavior tests pass.
- Changed-scope coverage remains at least 95%.
- The registered probe keeps descriptor/stat counters at zero where expected and shows a lower local elapsed mean than the captured baseline.
