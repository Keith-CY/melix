# Runtime Utils Top-level Weight Entry Binding Slice

## Scope

This Python-only performance slice is limited to `services/mlx-worker-python/worker/runtime/runtime_utils.py`, specifically the top-level model weight file scan used by `estimate_model_weight_resident_bytes()` when no valid safetensors index is available.

## Probe Coverage

The affected path is covered by the registered PR-scoped probe `runtime-utils-top-level-weight-streaming` in `infra/perf/pr_scoped_probes.json`. The registry already includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/runtime_utils.py`
- `services/mlx-worker-python/tests/test_runtime_utils.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/runtime_utils_top_level_weights_probe.py`

## Implementation Plan

1. Keep the existing `os.scandir()` streaming behavior and suffix semantics unchanged.
2. Bind `_weight_dir_entry_file_size` once before the scan loop to avoid repeated global lookup on large top-level model bundles.
3. Reuse existing focused tests for indexed fallback, top-level scanning, error handling, and PR-scoped probe registration.
4. Run focused pytest, changed-scope coverage, and the registered local probe on Linux before opening the PR.
5. Use GitHub Actions PR-scoped performance output as the merge gate.

## Linux Validation Boundary

This slice changes Python worker code only and is locally verifiable on Linux. Swift runtime effects are not involved.
