# Runtime utils top-level weight file stat check fast path

## Scope

This Python-only performance slice is limited to `worker/runtime/runtime_utils.py`, specifically the regular-file check used while summing top-level local model weight files. The affected helper is `_weight_dir_entry_file_size(...)`, which is called once per candidate directory entry after filename filtering.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `runtime-utils-top-level-weight-streaming` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/runtime_utils.py`
- `services/mlx-worker-python/tests/test_runtime_utils.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/runtime_utils_top_level_weights_probe.py`

The probe reports both top-level directory scanning metrics and indexed safetensors metrics. This slice uses `elapsed_ms_mean` and `peak_bytes_mean` as the primary metrics; indexed metrics are monitored as context because the indexed path still uses `_weight_file_size(...)`.

## Optimization slice

The hot top-level scan helper already filters candidate filenames before stat calls and uses a single stat result for file type plus byte size. This follow-up binds `stat.S_ISREG` once at module import as `_S_ISREG` and reuses that direct callable in `_weight_dir_entry_file_size(...)`, avoiding repeated module attribute lookup in the per-entry stat loop while preserving file-type semantics and `OSError` handling. `_weight_file_size(...)` is intentionally unchanged so indexed-shard context metrics remain isolated from this top-level directory scan slice.

## Verification plan

Run the focused registered test command, changed-scope coverage command, and registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.

## Linux verification boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime effect is claimed.
