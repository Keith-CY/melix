# Native MTP model safetensor name loop slice

This Python-only performance slice is limited to the native-MTP loader's top-level `model*.safetensors` listing helper in `services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py`.

## Scope

Registered PR-scoped probe: `native-mtp-loader-safetensor-scandir` in `infra/perf/pr_scoped_probes.json`.

The prior helper used a list comprehension that read `entry.name` twice for every directory entry while filtering a large model directory. This slice keeps the existing `os.scandir()` behavior and sorted `glob`-compatible output, but switches the hot path to an explicit loop that binds `entry.name` once and reuses a bound append method.

The probe is extended to measure the model safetensor listing path directly against the historical `glob.glob(str(model_dir / "model*.safetensors"))` baseline, while preserving the existing index JSON, sidecar shard, and key predicate metrics.

## Verification plan

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_index_payload_loads_from_bytes services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_weight_key_detection_preserves_string_and_custom_keys services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_model_safetensor_listing_uses_scandir_without_glob services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_extra_safetensor_files_filters_names_before_path_join services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_preload_patch_detects_qwen36_mtp_weights services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_patched_loader_uses_scandir_model_weight_listing services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_native_mtp_loader_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_native_mtp_loader_safetensor_scandir_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run --source=worker.runtime.native_mtp.mlx_lm_loader -m pytest -q services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_index_payload_loads_from_bytes services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_weight_key_detection_preserves_string_and_custom_keys services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_model_safetensor_listing_uses_scandir_without_glob services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_extra_safetensor_files_filters_names_before_path_join services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_preload_patch_detects_qwen36_mtp_weights services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_patched_loader_uses_scandir_model_weight_listing && uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_NATIVE_MTP_LOADER_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python bash -c 'SCRIPT="scripts/native_mtp_loader_safetensor_scandir_probe.py"; python3 "$SCRIPT"'
```

## Success criteria

- Focused native-MTP tests pass locally on Linux.
- Changed-scope coverage for `mlx_lm_loader.py` remains at least 95%.
- Registered probe emits `model_listing_*` metrics and keeps behavior parity with the `glob` baseline.
- `model_listing_new_mean_ms` is lower than `model_listing_old_mean_ms` on the local Linux probe run or CI report.
