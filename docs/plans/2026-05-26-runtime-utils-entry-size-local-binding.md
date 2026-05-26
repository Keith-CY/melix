# Runtime utils top-level weight entry-size local binding

## Scope

This Python-only performance slice is limited to `worker.runtime.runtime_utils._top_level_weight_file_bytes()`.
It preserves model weight resident-byte semantics while reducing repeated global helper lookup overhead during flat model-bundle scans.

## Registered performance probe

The existing `runtime-utils-top-level-weight-streaming` PR-scoped probe covers:

- `services/mlx-worker-python/worker/runtime/runtime_utils.py`
- `services/mlx-worker-python/tests/test_runtime_utils.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/runtime_utils_top_level_weights_probe.py`

The registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries, so this slice does not need probe registration changes.

## Plan

1. Bind `_weight_dir_entry_file_size` once before the directory-entry loop in `_top_level_weight_file_bytes()`.
2. Keep the existing `os.scandir()` streaming behavior and error handling unchanged.
3. Run the registered focused tests, changed-scope coverage, and local registered probe on Linux.
4. Use the PR-scoped performance workflow as the CI merge gate.

## Verification

Run the registered probe commands from `infra/perf/pr_scoped_probes.json` for `runtime-utils-top-level-weight-streaming` locally before opening the PR. CI remains the source of truth for the registered PR-scoped performance report.
