# Runtime utils missing safetensors index stat fast path

## Scope

Optimize one Python hot path in `services/mlx-worker-python/worker/runtime/runtime_utils.py`: local model weight estimation for flat model directories that do not have `model.safetensors.index.json`.

## Probe Coverage

The affected path is covered by the registered PR-scoped probe `runtime-utils-top-level-weight-streaming` in `infra/perf/pr_scoped_probes.json`. The entry includes focused `test_command`, `coverage_command`, and `probe_command` values for:

- `services/mlx-worker-python/worker/runtime/runtime_utils.py`
- `services/mlx-worker-python/tests/test_runtime_utils.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/runtime_utils_top_level_weights_probe.py`

This slice extends the focused test/coverage commands with a regression test proving missing safetensors indexes are not opened before falling back to the top-level weight scan.

## Implementation Plan

1. Before parsing `model.safetensors.index.json`, check whether the index path is a file.
2. If the index is absent, return `0` immediately so `estimate_model_weight_resident_bytes(...)` falls back to the existing top-level `os.scandir(...)` scan without paying repeated missing-file open/exception overhead.
3. Preserve existing behavior for malformed indexes, unreadable indexes, indexed unique shards, direct files, unreadable directories, and top-level weight scans.

## Verification

Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux. Compare the probe against the pre-change baseline from the same worktree and report the mean elapsed delta.
