# Native MTP Extra Shard Duplicate Filter Performance Slice

## Scope

This Python-only performance slice narrows the native-MTP sidecar shard discovery
loop in `services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py`.

The slice keeps behavior unchanged while moving the duplicate `seen` check ahead
of basename extraction for candidate `.safetensors` sidecar entries. Duplicate
index entries now skip the path-separator/basename branch before joining or
checking the filesystem.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`native-mtp-loader-safetensor-scandir` in `infra/perf/pr_scoped_probes.json`.
The probe already has focused `test_command`, `coverage_command`, and
`probe_command` entries for this loader and its tests.

Required local commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_extra_safetensor_files_filters_names_before_path_join \
  services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_extra_safetensor_files_preserves_custom_file_names \
  services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_load_weight_shards_streams_base_and_extra_paths \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_native_mtp_loader_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_native_mtp_loader_safetensor_scandir_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run --source=worker.runtime.native_mtp.mlx_lm_loader -m pytest -q \
  services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_extra_safetensor_files_filters_names_before_path_join \
  services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_extra_safetensor_files_preserves_custom_file_names \
  services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_load_weight_shards_streams_base_and_extra_paths \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_native_mtp_loader_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_native_mtp_loader_safetensor_scandir_probe_script_emits_metrics && \
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && \
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_NATIVE_MTP_LOADER_REPO_ROOT="$PWD" \
  MELIX_NATIVE_MTP_LOADER_SAMPLES=7 MELIX_NATIVE_MTP_LOADER_DISTRACTOR_FILES=2000 \
  uv run --project services/mlx-worker-python python3 scripts/native_mtp_loader_safetensor_scandir_probe.py
```

## Decision Rule

Accept only if focused tests and changed-scope coverage pass and the registered
probe shows non-regression with a clear improvement in `extra_new_mean_ms` or
related native-MTP sidecar metrics. PR-scoped performance CI remains the merge
gate for the registered probe.
