# Runtime Utils Weight Suffix Fast Path

## Scope

This performance slice is limited to the Python worker helper that scans top-level model weight files in `services/mlx-worker-python/worker/runtime/runtime_utils.py`.

## Registered Probe

Affected path is covered by the registered PR-scoped probe `runtime-utils-top-level-weight-streaming` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and repeatedly calls `estimate_model_weight_resident_bytes(...)` over a synthetic flat model directory. Relevant metrics:

- `elapsed_ms_mean` (`lower_is_better`)
- `peak_bytes_mean` (`lower_is_better`)

## Optimization Slice

`_weight_dir_entry_file_size(...)` previously used `os.path.splitext(entry.name)[1].lower()` for every scanned directory entry. Most generated and downloaded model weight files already use lowercase suffixes, so the slice adds a lowercase-suffix fast path using `str.endswith(...)` before falling back to the case-insensitive path for mixed-case compatibility.

This keeps behavior unchanged for mixed-case suffixes while avoiding `splitext(...)` tuple construction and suffix normalization on the common lowercase weight-file path.

## Verification Plan

Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux before opening a PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_runtime_utils.py::test_estimate_model_weight_resident_bytes_uses_indexed_unique_shards services/mlx-worker-python/tests/test_runtime_utils.py::test_estimate_model_weight_resident_bytes_falls_back_to_top_level_weights services/mlx-worker-python/tests/test_runtime_utils.py::test_top_level_weight_file_bytes_streams_iterdir_entries services/mlx-worker-python/tests/test_runtime_utils.py::test_top_level_weight_file_bytes_handles_direntry_non_files_and_errors services/mlx-worker-python/tests/test_runtime_utils.py::test_estimate_model_weight_resident_bytes_ignores_malformed_index_and_unreadable_directory services/mlx-worker-python/tests/test_runtime_utils.py::test_estimate_model_weight_resident_bytes_handles_file_missing_and_stat_errors services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_runtime_utils_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_runtime_utils_top_level_weights_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_runtime_utils.py::test_estimate_model_weight_resident_bytes_uses_indexed_unique_shards services/mlx-worker-python/tests/test_runtime_utils.py::test_estimate_model_weight_resident_bytes_falls_back_to_top_level_weights services/mlx-worker-python/tests/test_runtime_utils.py::test_top_level_weight_file_bytes_streams_iterdir_entries services/mlx-worker-python/tests/test_runtime_utils.py::test_top_level_weight_file_bytes_handles_direntry_non_files_and_errors services/mlx-worker-python/tests/test_runtime_utils.py::test_estimate_model_weight_resident_bytes_ignores_malformed_index_and_unreadable_directory services/mlx-worker-python/tests/test_runtime_utils.py::test_estimate_model_weight_resident_bytes_handles_file_missing_and_stat_errors services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_runtime_utils_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_runtime_utils_top_level_weights_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/runtime_utils.py services/mlx-worker-python/tests/test_runtime_utils.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/runtime_utils_top_level_weights_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/runtime_utils_top_level_weights_probe.py
```

CI remains the merge gate for the registered PR-scoped performance report.
