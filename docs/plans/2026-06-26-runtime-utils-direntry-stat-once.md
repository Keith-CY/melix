# Runtime utils DirEntry stat once

## Goal

Reduce per-entry filesystem calls in the Python runtime weight-size estimator by using a single `DirEntry.stat()` result for top-level model weight candidates.

## Scope

This Python-only performance slice is limited to:

- `services/mlx-worker-python/worker/runtime/runtime_utils.py`
- `services/mlx-worker-python/tests/test_runtime_utils.py`

The slice preserves the existing filename suffix filters, missing-file tolerance, non-regular-file filtering, and resident-byte totals.

## Registered probe

The affected path is covered by the registered PR-scoped probe `runtime-utils-top-level-weight-streaming` in `infra/perf/pr_scoped_probes.json`.

The registered probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for the runtime utility path, its focused tests, PR-scoped performance selection tests, and `scripts/runtime_utils_top_level_weights_probe.py`.

## Optimization hypothesis

`_weight_dir_entry_file_size()` previously called `DirEntry.is_file()` and then `DirEntry.stat()` for weight-like filenames. On filesystems where `is_file()` may need metadata, this can duplicate per-entry metadata work. Calling `DirEntry.stat()` once and checking `stat.S_ISREG(st_mode)` reuses the same metadata payload for both regular-file filtering and byte-size accounting.

## Verification path

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_runtime_utils.py::test_estimate_model_weight_resident_bytes_uses_indexed_unique_shards \
  services/mlx-worker-python/tests/test_runtime_utils.py::test_estimate_model_weight_resident_bytes_falls_back_to_top_level_weights \
  services/mlx-worker-python/tests/test_runtime_utils.py::test_estimate_model_weight_resident_bytes_skips_missing_index_read \
  services/mlx-worker-python/tests/test_runtime_utils.py::test_top_level_weight_file_bytes_streams_iterdir_entries \
  services/mlx-worker-python/tests/test_runtime_utils.py::test_top_level_weight_file_bytes_handles_direntry_non_files_and_errors \
  services/mlx-worker-python/tests/test_runtime_utils.py::test_estimate_model_weight_resident_bytes_ignores_malformed_index_and_unreadable_directory \
  services/mlx-worker-python/tests/test_runtime_utils.py::test_estimate_model_weight_resident_bytes_handles_file_missing_and_stat_errors \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_runtime_utils_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_runtime_utils_top_level_weights_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same focused tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/runtime/runtime_utils.py \
  services/mlx-worker-python/tests/test_runtime_utils.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/runtime_utils_top_level_weights_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/runtime_utils_top_level_weights_probe.py
```

## Success criteria

- Focused tests pass.
- Changed-scope automated coverage is at least 95%.
- Local registered probe shows non-regression or improvement for `elapsed_ms_mean` and `peak_bytes_mean`.
- Hosted `runtime-utils-top-level-weight-streaming` PR-scoped CI completes successfully before merge.
