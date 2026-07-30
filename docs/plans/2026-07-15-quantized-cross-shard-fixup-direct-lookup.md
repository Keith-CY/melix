# Quantized cross-shard fixup direct lookup

## Scope

This Python-only performance slice is limited to
`cross_shard_quantized_metadata_fixup_count(...)` in
`services/mlx-worker-python/worker/runtime/quantized_tensor_metadata.py`.

The function runs after quantized metadata prepass construction to count modules
whose `.weight` and `.scales` tensors live on different safetensors shards. Before
this slice it reused `QuantizedTensorMetadata.quantized_tensor_shards(...)` for
each candidate prefix, allocating a short-lived dictionary per prefix even though
only two direct shard lookups are needed.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`quantized-tensor-metadata-prepass` in `infra/perf/pr_scoped_probes.json`. This
slice extends that probe with focused cross-shard fixup metrics while keeping the
existing focused `test_command`, `coverage_command`, and `probe_command` entries:

- `cross_shard_fixup_elapsed_ms_mean`
- `cross_shard_fixup_peak_bytes_mean`
- `cross_shard_fixup_count`

## Plan

1. Add regression coverage proving cross-shard fixup counting no longer calls the
   per-prefix shard-dictionary helper.
2. Build separate prefix-to-shard maps for `.weight` and `.scales` entries, then
   compare the smaller side against the other without allocating a per-prefix
   shard dictionary.
3. Extend the registered probe and registry metrics to report repeated fixup
   count cost.
4. Run focused pytest, changed-scope coverage, and the registered probe locally
   on Linux before opening the PR.
5. Use GitHub Actions and the registered PR-scoped performance report as the
   merge gate.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_index_payload_loads_from_bytes services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_quantized_tensor_metadata_merges_cross_shard_index_and_headers services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_cross_shard_quantized_metadata_fixup_count_avoids_shard_dict_allocation services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_quantized_tensor_metadata_reads_string_shard_paths_without_path_open services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_quantized_tensor_metadata_normalizes_index_keys_once services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_quantized_tensor_metadata_model_dir_scans_top_level_headers_and_bad_entries services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_quantized_scales_present_skips_empty_weight_lookup services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_multimodal_high_precision_module_segment_scan_preserves_boundaries services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_patched_loader_uses_scandir_model_weight_listing services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_gemma4_text_only_language_model_quantizes_from_presanitize_metadata services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_gemma4_text_backed_loader_uses_tokenizer_for_text_only_exports services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_mlx_vlm_runtime_uses_generate_step_for_mtp_when_available services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_native_mtp_loader_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_quantized_tensor_metadata_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_mlx_vlm_runtime_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_quantized_tensor_metadata_prepass_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_quantized_tensor_metadata_prepass_probe_base_fallback services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run --include='*/services/mlx-worker-python/worker/runtime/quantized_tensor_metadata.py,*/services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py,*/services/mlx-worker-python/worker/runtime/mlx_vlm_runtime.py,*/services/mlx-worker-python/tests/test_mlx_vlm_runtime.py,*/services/mlx-worker-python/tests/test_pr_scoped_performance.py,*/scripts/quantized_tensor_metadata_prepass_probe.py' -m pytest -q <same focused tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/quantized_tensor_metadata.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/quantized_tensor_metadata_prepass_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_QUANTIZED_TENSOR_METADATA_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/quantized_tensor_metadata_prepass_probe.py
```
