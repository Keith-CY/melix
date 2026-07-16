# Model registry JSON loader local binding slice

This Python performance slice is limited to JSON dictionary loading in
`worker.model_registry.catalog._load_json_dict_file(...)`.

## Registered probe

The affected path is covered by the PR-scoped registered probe
`model-registry-plain-local-manifest-stat-elision` in
`infra/perf/pr_scoped_probes.json`. The probe watches the model registry
catalog, focused tests, and registry entry. It includes focused `test_command`,
`coverage_command`, and `probe_command` entries.

The probe exercises a synthetic plain-local registry with 400 model directories,
measuring catalog scan elapsed time while confirming the existing manifest and
missing generation-config stat-elision behavior stays intact.

## Implementation plan

1. Preserve JSON file semantics for regular-file checks, cache reuse, decode
   failures, and non-object JSON payloads.
2. Bind the JSON decoder at module scope so hot config loads avoid repeated
   module attribute lookup during large local registry scans.
3. Extend focused regression coverage to assert the bound decoder path is used
   together with the existing byte-read and cache behavior.
4. Run the registered local test, changed-scope coverage, and probe on Linux;
   GitHub PR-scoped performance remains the merge gate.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_records_plain_local_weight_presence_during_single_scandir_pass services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_skips_hf_prune_relative_probe_for_plain_dirs services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_plain_local_tree_scan_and_config_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_skips_runtime_rebuild_when_cached_snapshot_is_current services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_missing_plain_local_generation_config_after_tree_scan services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_imports_plain_local_generation_config_when_seen_during_tree_scan services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_hf_cache_config_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_raw_model_spec_loads_config_payload_when_not_supplied services/mlx-worker-python/tests/test_model_registry_catalog.py::test_metadata_payload_direct_mlx_signal_accepts_exact_and_normalized_values services/mlx-worker-python/tests/test_model_registry_catalog.py::test_metadata_payload_has_mlx_signal_skips_json_for_direct_metadata services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_empty_supplied_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_skips_config_text_fallback_for_nonempty_payload_without_mlx_signal services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_unserializable_nonempty_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_load_json_dict_file_reads_json_bytes_without_text_decode services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_records_plain_local_weight_presence_during_single_scandir_pass services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_skips_hf_prune_relative_probe_for_plain_dirs services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_plain_local_tree_scan_and_config_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_skips_runtime_rebuild_when_cached_snapshot_is_current services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_missing_plain_local_generation_config_after_tree_scan services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_imports_plain_local_generation_config_when_seen_during_tree_scan services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_hf_cache_config_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_raw_model_spec_loads_config_payload_when_not_supplied services/mlx-worker-python/tests/test_model_registry_catalog.py::test_metadata_payload_direct_mlx_signal_accepts_exact_and_normalized_values services/mlx-worker-python/tests/test_model_registry_catalog.py::test_metadata_payload_has_mlx_signal_skips_json_for_direct_metadata services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_empty_supplied_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_skips_config_text_fallback_for_nonempty_payload_without_mlx_signal services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_unserializable_nonempty_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_load_json_dict_file_reads_json_bytes_without_text_decode services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py docs/plans/2026-07-15-model-registry-json-loads-local-bind.md
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --probe-id model-registry-plain-local-manifest-stat-elision --base-ref origin/main --head-ref HEAD --output-json /tmp/model-registry-json-loads-local-bind-pr-scope.json
```
