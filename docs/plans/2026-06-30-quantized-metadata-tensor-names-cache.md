# Quantized metadata tensor-name snapshot cache

## Scope

This Python-only performance slice is limited to `QuantizedTensorMetadata.tensor_names`
in `services/mlx-worker-python/worker/runtime/quantized_tensor_metadata.py`.

`tensor_names` is a convenience snapshot used by model-dir/header fallback paths
and probe/report code. Before this slice each property access rebuilt a
`frozenset` from the immutable mapping. The metadata object is already immutable,
so the tensor-name snapshot can be built once during normalization and reused.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`quantized-tensor-metadata-prepass` in `infra/perf/pr_scoped_probes.json`.

This slice extends the existing registered probe with focused `tensor_names`
access metrics while keeping the same focused `test_command`, `coverage_command`,
and `probe_command` structure:

- `tensor_names_access_elapsed_ms_mean`
- `tensor_names_access_peak_bytes_mean`
- `tensor_names_access_count`

## Plan

1. Add regression coverage proving `tensor_names` returns the normalized immutable
   snapshot and reuses the same frozenset object on repeated access.
2. Cache the frozenset during `QuantizedTensorMetadata` construction and in the
   normalized-mapping fast path used by index/header parsing.
3. Extend the registered probe script and registry metrics to measure repeated
   tensor-name snapshot access.
4. Run focused pytest, changed-scope coverage, and the registered probe locally
   on Linux before opening the PR.
5. Use GitHub Actions and the registered PR-scoped performance report as the
   merge gate.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_quantized_tensor_metadata_merges_cross_shard_index_and_headers services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_quantized_tensor_metadata_normalizes_index_keys_once services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_quantized_tensor_metadata_model_dir_scans_top_level_headers_and_bad_entries services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_quantized_scales_present_skips_empty_weight_lookup services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_multimodal_high_precision_module_segment_scan_preserves_boundaries services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_patched_loader_uses_scandir_model_weight_listing services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_gemma4_text_only_language_model_quantizes_from_presanitize_metadata services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_gemma4_text_backed_loader_uses_tokenizer_for_text_only_exports services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_mlx_vlm_runtime_uses_generate_step_for_mtp_when_available services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_native_mtp_loader_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_quantized_tensor_metadata_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_mlx_vlm_runtime_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_quantized_tensor_metadata_prepass_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_quantized_tensor_metadata_prepass_probe_base_fallback services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run --include='*/services/mlx-worker-python/worker/runtime/quantized_tensor_metadata.py,*/services/mlx-worker-python/tests/test_mlx_vlm_runtime.py,*/services/mlx-worker-python/tests/test_pr_scoped_performance.py,*/scripts/quantized_tensor_metadata_prepass_probe.py' -m pytest -q services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_quantized_tensor_metadata_merges_cross_shard_index_and_headers services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_quantized_tensor_metadata_normalizes_index_keys_once services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_quantized_tensor_metadata_model_dir_scans_top_level_headers_and_bad_entries services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_quantized_scales_present_skips_empty_weight_lookup services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_quantized_tensor_metadata_prepass_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_quantized_tensor_metadata_prepass_probe_base_fallback services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/quantized_tensor_metadata.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/quantized_tensor_metadata_prepass_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_QUANTIZED_TENSOR_METADATA_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/quantized_tensor_metadata_prepass_probe.py
```
