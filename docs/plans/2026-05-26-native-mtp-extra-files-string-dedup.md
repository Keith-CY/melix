# Native MTP extra shard string dedup

## Scope

This Python-only performance slice is limited to native-MTP sidecar shard discovery in `services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py`.

`extra_mtp_safetensor_files()` can see repeated MTP weight-map entries that point to the same non-model sidecar shard. The previous sidecar fast path filtered ordinary `model*.safetensors` and non-safetensor names before joining paths, but duplicate sidecar names still repeated `Path` joins before the `Path`-based `seen` set removed them.

This slice keeps output ordering and existence checks unchanged for first-seen sidecar names while deduplicating by file-name string before constructing a `Path`.

## Registered probe

Affected path coverage uses the existing registered PR-scoped probe `native-mtp-loader-safetensor-scandir` in `infra/perf/pr_scoped_probes.json`.

The probe already includes focused `test_command`, `coverage_command`, and `probe_command` entries covering:

- `services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py`
- `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/native_mtp_loader_safetensor_scandir_probe.py`

This slice updates the probe workload to include duplicate native-MTP sidecar index entries and reports `duplicate_mtp_entries` alongside the existing sidecar timing metrics.

## Implementation plan

1. Extend the sidecar regression test so duplicate sidecar entries must not repeat `Path` joins.
2. Replace `seen: set[Path]` with `seen: set[str]` after string-level sidecar name filtering and before path construction.
3. Extend the registered probe workload with duplicate MTP entries so local and CI probe metrics exercise the new path.
4. Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux before PR creation. CI remains the final registered PR-scoped performance gate.

## Validation commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_index_payload_loads_from_bytes services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_model_safetensor_listing_uses_scandir_without_glob services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_extra_safetensor_files_filters_names_before_path_join services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_preload_patch_detects_qwen36_mtp_weights services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_patched_loader_uses_scandir_model_weight_listing services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_native_mtp_loader_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_native_mtp_loader_safetensor_scandir_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run --source=worker.runtime.native_mtp.mlx_lm_loader -m pytest -q services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_index_payload_loads_from_bytes services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_model_safetensor_listing_uses_scandir_without_glob services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_extra_safetensor_files_filters_names_before_path_join services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_preload_patch_detects_qwen36_mtp_weights services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_patched_loader_uses_scandir_model_weight_listing && uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_NATIVE_MTP_LOADER_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python bash -c 'SCRIPT="scripts/native_mtp_loader_safetensor_scandir_probe.py"; python3 "$SCRIPT"'
```
