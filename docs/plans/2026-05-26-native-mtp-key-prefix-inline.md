# Native MTP key prefix inline fast path

## Scope

This Python-only performance slice is limited to native-MTP sidecar shard
discovery in `services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py`.
The behavior remains unchanged: only MTP weight-map keys with
`language_model.mtp.` or `mtp.` prefixes can contribute non-`model*.safetensors`
sidecar shard paths, duplicates are still skipped, missing files are still
warned and ignored, and the top-level model shard listing keeps the existing
`os.scandir()` path.

## Probe coverage

The affected path is already covered by the registered PR-scoped performance
probe `native-mtp-loader-safetensor-scandir` in
`infra/perf/pr_scoped_probes.json`. That entry has focused `test_command`,
`coverage_command`, and `probe_command` values for the native-MTP loader,
focused tests, and `scripts/native_mtp_loader_safetensor_scandir_probe.py`.

## Plan

1. Keep the registered probe definition stable; do not mix registry behavior
   changes with this runtime slice.
2. Preserve behavior with the existing focused native-MTP regression tests,
   including duplicate sidecar filtering and avoiding unnecessary path joins.
3. Inline the MTP key prefix check inside the weight-map loop so JSON string
   keys avoid the per-entry helper call and unconditional `str()` conversion,
   while retaining the fallback conversion for non-string mappings.
4. Run focused pytest, changed-scope coverage, and the registered probe locally
   on Linux before opening the PR.
5. Use GitHub Actions and the registered PR-scoped performance report as the
   merge gate.

## Local verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_index_payload_loads_from_bytes services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_model_safetensor_listing_uses_scandir_without_glob services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_extra_safetensor_files_filters_names_before_path_join services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_preload_patch_detects_qwen36_mtp_weights services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_patched_loader_uses_scandir_model_weight_listing services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_native_mtp_loader_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_native_mtp_loader_safetensor_scandir_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run --source=worker.runtime.native_mtp.mlx_lm_loader -m pytest -q services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_index_payload_loads_from_bytes services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_model_safetensor_listing_uses_scandir_without_glob services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_extra_safetensor_files_filters_names_before_path_join services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_preload_patch_detects_qwen36_mtp_weights services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_patched_loader_uses_scandir_model_weight_listing && uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_NATIVE_MTP_LOADER_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/native_mtp_loader_safetensor_scandir_probe.py
```
