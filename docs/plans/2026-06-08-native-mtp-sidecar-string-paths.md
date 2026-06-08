# Native MTP sidecar string paths slice

## Scope

This Python-only performance slice is limited to the native-MTP loader sidecar shard path handling in `services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py`.

## Registered probe

Registered PR-scoped probe: `native-mtp-loader-safetensor-scandir` in `infra/perf/pr_scoped_probes.json`.

The probe already covers the affected path and provides focused `test_command`, `coverage_command`, and `probe_command` entries. This slice keeps the same probe and extends `scripts/native_mtp_loader_safetensor_scandir_probe.py` so the weight-load metric measures the patched loader's string sidecar path flow.

## Change

The patched `mlx_lm.utils.load_model` path does not need public `Path` objects for native-MTP sidecar shards because `mx.load(...)` receives string paths. This slice adds a private `_extra_mtp_safetensor_file_paths(...)` helper returning validated sidecar shard paths as strings, keeps the public `extra_mtp_safetensor_files(...)` wrapper for existing behavior, and passes string sidecars directly to `_load_weight_shards(...)` to avoid per-sidecar `Path(...)` and `str(Path)` conversions on the hot load path.

## Verification plan

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_extra_safetensor_files_preserves_custom_file_names services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_extra_safetensor_files_filters_names_before_path_join services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_load_weight_shards_streams_base_and_extra_paths services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_patched_loader_uses_scandir_model_weight_listing services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_native_mtp_loader_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_native_mtp_loader_safetensor_scandir_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_extra_safetensor_files_preserves_custom_file_names services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_extra_safetensor_files_filters_names_before_path_join services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_load_weight_shards_streams_base_and_extra_paths services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_patched_loader_uses_scandir_model_weight_listing services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_native_mtp_loader_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_native_mtp_loader_safetensor_scandir_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/native_mtp_loader_safetensor_scandir_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_NATIVE_MTP_LOADER_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/native_mtp_loader_safetensor_scandir_probe.py
```

## Expected result

Behavior remains equivalent for public sidecar discovery, while the patched loader's sidecar loading path avoids unnecessary path object round-trips. Accept the slice only if focused tests, changed-scope coverage, and the registered probe pass without a regression.
