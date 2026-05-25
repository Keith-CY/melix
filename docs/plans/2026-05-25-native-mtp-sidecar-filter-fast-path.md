# Native MTP sidecar filter fast path

## Scope

This Python-only performance slice is limited to native-MTP sidecar shard discovery in `services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py`.

`extra_mtp_safetensor_files()` walks `model.safetensors.index.json` entries to attach native-MTP sidecar shards. The previous implementation joined every MTP weight-map file name to `model_path` before filtering out ordinary `model*.safetensors` shards or non-safetensor names. Large indexes with many ordinary MTP-prefixed records therefore paid avoidable `Path` join/allocation cost.

## Registered probe

Affected path coverage uses the existing registered PR-scoped probe `native-mtp-loader-safetensor-scandir` in `infra/perf/pr_scoped_probes.json`.

This slice extends that probe and its focused test command to include sidecar shard filtering metrics while preserving the existing index JSON byte-loading and scandir model-shard listing checks.

## Implementation plan

1. Add a regression test proving sidecar filtering skips irrelevant index names before joining them to `model_path`.
2. Filter sidecar file names with basename string checks before constructing candidate `Path` objects.
3. Extend `scripts/native_mtp_loader_safetensor_scandir_probe.py` to compare baseline sidecar listing against the optimized helper and emit sidecar-specific timing/peak-memory metrics.
4. Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux before PR creation. CI remains the final registered PR-scoped performance gate.

## Validation commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_index_payload_loads_from_bytes services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_model_safetensor_listing_uses_scandir_without_glob services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_extra_safetensor_files_filters_names_before_path_join services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_preload_patch_detects_qwen36_mtp_weights services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_patched_loader_uses_scandir_model_weight_listing services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_native_mtp_loader_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_native_mtp_loader_safetensor_scandir_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run --source=worker.runtime.native_mtp.mlx_lm_loader -m pytest -q services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_index_payload_loads_from_bytes services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_model_safetensor_listing_uses_scandir_without_glob services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_extra_safetensor_files_filters_names_before_path_join services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_preload_patch_detects_qwen36_mtp_weights services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_patched_loader_uses_scandir_model_weight_listing && uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_NATIVE_MTP_LOADER_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python bash -c 'SCRIPT="scripts/native_mtp_loader_safetensor_scandir_probe.py"; python3 "$SCRIPT"'
```
