# Runtime utils lowercase non-weight filename fast path

## Scope

This Python-only performance slice is limited to top-level model weight byte estimation in `services/mlx-worker-python/worker/runtime/runtime_utils.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `runtime-utils-top-level-weight-streaming` in `infra/perf/pr_scoped_probes.json`. That registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the runtime utils top-level weight scan path.

## Optimization

The top-level weight scan checks every directory entry with `_is_model_weight_filename()` before calling `DirEntry.is_file()` and `DirEntry.stat()`. Synthetic and real model bundles commonly include many lowercase non-weight files such as `README.md`, tokenizer JSON, and text artifacts. After the exact lowercase weight suffix check fails, this slice uses `str.islower()` to reject lowercase non-weight names without allocating a lowercase copy. Mixed-case weight suffixes still fall back to `name.lower()` so existing case-insensitive weight detection is preserved.

## Verification Plan

- Run focused runtime utility tests for indexed and top-level weight accounting.
- Run changed-scope coverage through the registered probe coverage command.
- Run the registered `runtime-utils-top-level-weight-streaming` probe locally on Linux before and after the change and compare `elapsed_ms_mean` and `peak_bytes_mean`.

## Linux Boundary

This slice is Python-only and locally verifiable on Linux. Swift/macOS runtime effects are not involved.
