# Model Registry Weight Suffix Constant

Date: 2026-06-06

## Scope

This Python-only performance slice is limited to the model-registry weight-file
suffix checks in `services/mlx-worker-python/worker/model_registry/catalog.py`.

## Problem

The plain-local registry scan checks file names for model weight suffixes in two
hot paths: `_has_model_weight_files(...)` and the single-pass registry tree scan.
Both paths previously supplied the same literal suffix tuple at each call site.
The repeated literal is small, but the registered probe scans hundreds of
synthetic model directories and repeatedly exercises the suffix check while
preserving descriptor/stat counters.

## Plan

- Add a module-level `_MODEL_WEIGHT_FILE_SUFFIXES` tuple next to the existing
  registry scan constants.
- Reuse that tuple from both model weight suffix checks.
- Keep discovery behavior, traversal order, manifest parsing, and JSON/protobuf
  behavior unchanged.
- Reuse the existing registered PR-scoped probe
  `model-registry-plain-local-manifest-stat-elision`.

## Registered Probe

Registered PR-scoped probe: `model-registry-plain-local-manifest-stat-elision` in
`infra/perf/pr_scoped_probes.json`.

The registry entry already includes focused `test_command`, `coverage_command`,
and `probe_command` entries covering `catalog.py`, focused catalog tests,
PR-scoped performance tests, and the synthetic 400-model registry scan metrics.

## Local Evidence

Linux verification on this branch:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_records_plain_local_weight_presence_during_single_scandir_pass services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_skips_hf_prune_relative_probe_for_plain_dirs services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_plain_local_tree_scan_and_config_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_skips_runtime_rebuild_when_cached_snapshot_is_current services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_missing_plain_local_generation_config_after_tree_scan services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_imports_plain_local_generation_config_when_seen_during_tree_scan services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_hf_cache_config_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_raw_model_spec_loads_config_payload_when_not_supplied services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_empty_supplied_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_skips_config_text_fallback_for_nonempty_payload_without_mlx_signal services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_unserializable_nonempty_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_metadata_payload_has_mlx_signal_does_not_request_sorted_json services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_config_payload_fast_path_avoids_json_dump services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_plain_local_manifest_after_tree_scan services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_skips_invalid_depth_manifests_without_parsing services/mlx-worker-python/tests/test_model_registry_catalog.py::test_load_json_dict_file_reads_json_bytes_without_text_decode services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id model-registry-plain-local-manifest-stat-elision --base-repo /root/.hermes/profiles/coder/workspace/worktrees/melix-perf-base-model-registry-20260606 --head-repo "$PWD" --output /tmp/model_registry_manifest_suffix_probe.json
```

Results:

- Focused tests: `19 passed in 1.54s`.
- Changed-scope coverage: `TOTAL 3 0 100%`.
- Registered probe: base `elapsed_ms_mean=113.221575`, head
  `elapsed_ms_mean=112.329853`, delta `-0.891722 ms` (`~0.79%` faster).
- Semantic counters unchanged: `generation_config_stat_calls_mean=0`,
  `manifest_is_file_calls_mean=0`, `manifest_parse_calls_mean=0`,
  `config_load_calls_mean=400`, `discovered_model_count_mean=400`.

## Acceptance Criteria

- Focused behavior tests pass locally on Linux.
- Changed-scope coverage remains at least 95% for touched lines.
- Registered probe reports lower `elapsed_ms_mean` without changing semantic
  counters.
- PR-scoped performance CI completes successfully before merge.
