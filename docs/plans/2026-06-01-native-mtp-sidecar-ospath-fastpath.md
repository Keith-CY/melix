# Native MTP sidecar os.path fast path

## Scope

This Python-only performance slice is limited to `extra_mtp_safetensor_files()` in
`services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py`.
It keeps native-MTP sidecar discovery behavior unchanged while reducing per-entry
Path object and method dispatch overhead after the indexed sidecar name has
already passed the MTP key, duplicate, basename, and suffix filters.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`native-mtp-loader-safetensor-scandir` in `infra/perf/pr_scoped_probes.json`.
The registry already defines focused `test_command`, `coverage_command`, and
`probe_command` entries for the native-MTP loader path.

## Implementation Plan

1. Keep the existing index JSON byte-loading and MTP key filtering behavior.
2. Bind hot-loop helpers locally and use `os.path.join` / `os.path.exists` for
   existence checks before materializing the returned `Path` objects.
3. Keep the hot string-key predicate on the same explicit-prefix path as the
   probe baseline; reserve tuple-prefix fallback for non-string key objects.
4. Preserve the visible return type (`list[Path]`) and missing-shard warning.
5. Update the focused regression test so it asserts suffix filtering avoids
   unnecessary basename calls and that only accepted sidecar names reach the
   join/existence path.

## Verification

Run the focused native-MTP tests, changed-scope coverage command from the
registered probe, and the registered local probe on Linux. CI PR-scoped
performance remains the required base-vs-head merge gate.
