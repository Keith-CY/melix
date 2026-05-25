# Native MTP Index JSON Bytes Slice

## Scope

This Python-only performance slice is limited to native-MTP sidecar shard
detection in `worker.runtime.native_mtp.mlx_lm_loader`.

## Registered Probe

The affected path is covered by registered PR-scoped probe
`native-mtp-loader-safetensor-scandir` in `infra/perf/pr_scoped_probes.json`.
This slice extends that existing probe workload from only the safetensor shard
listing guard to the native-MTP `model.safetensors.index.json` payload read path.
The registry entry keeps focused `test_command`, `coverage_command`, and
`probe_command` fields and the probe script records read-text baseline versus
current loader JSON payload metrics.

## Implementation

`_load_json_payload()` should parse the index JSON directly from
`Path.read_bytes()` so JSON decoding can avoid the intermediate decoded string
copy produced by `Path.read_text(encoding="utf-8")`. Behavior remains unchanged:
missing files, invalid JSON, OS errors, and non-object payloads still return an
empty dictionary.

## Verification Plan

Run the focused registered test command, the changed-scope coverage command, and
the registered PR-scoped performance probe locally on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_index_payload_loads_from_bytes services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_model_safetensor_listing_uses_scandir_without_glob services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_preload_patch_detects_qwen36_mtp_weights services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_patched_loader_uses_scandir_model_weight_listing services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_native_mtp_loader_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_native_mtp_loader_safetensor_scandir_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run --source=worker.runtime.native_mtp.mlx_lm_loader -m pytest -q services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_index_payload_loads_from_bytes services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_model_safetensor_listing_uses_scandir_without_glob services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_preload_patch_detects_qwen36_mtp_weights services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_patched_loader_uses_scandir_model_weight_listing && uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py
MELIX_NATIVE_MTP_LOADER_PROBE_SCRIPT="$PWD/scripts/native_mtp_loader_safetensor_scandir_probe.py" PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id native-mtp-loader-safetensor-scandir --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/native-mtp-index-json-bytes-probe.json
```

CI PR-scoped performance remains the merge gate for the registered probe.
