# Native MTP file-name string fast path slice

## Goal

Reduce per-entry conversion overhead in native-MTP sidecar shard filtering by reusing exact `str` file names from the safetensors index weight map. The path still converts non-string file-name values with `str(...)`, preserves duplicate filtering, and keeps path joins delayed until after model-shard and suffix checks.

## Registered probe

The affected path is covered by the registered PR-scoped probe `native-mtp-loader-safetensor-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry provides focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py`
- `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/native_mtp_loader_safetensor_scandir_probe.py`

The probe reports model listing, index JSON loading, sidecar filtering, and MTP key predicate metrics against baseline implementations.

## Slice

- In `extra_mtp_safetensor_files`, skip `str(file_name)` for exact string file names, which are the normal JSON-decoded weight-map case.
- Mark each unique sidecar file name as seen immediately after the duplicate check so every skip/accept branch shares one `seen.add(...)` site.
- Keep the existing fallback conversion for custom/non-string file-name objects.
- Add regression coverage for custom file-name values to prevent the fast path from dropping non-string support.
- Do not change MTP key matching, missing-file warnings, duplicate handling, or model weight loading.

## Verification

Run the registered focused tests, changed-scope coverage command, and local registered probe on Linux before opening the PR. The PR-scoped performance workflow remains the merge gate for the registered probe result in CI.
