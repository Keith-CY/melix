# Native MTP Loader Extra-Path Local Bindings

## Scope

This Python-only performance slice is limited to
`services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py` and the
native-MTP sidecar shard discovery hot path. It preserves the existing behavior:
only top-level native-MTP `*.safetensors` sidecar shards referenced by the model
index are loaded, duplicate index entries are skipped, missing listed shards are
warned and ignored, and base `model*.safetensors` files remain excluded from the
sidecar list.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`native-mtp-loader-safetensor-scandir` in `infra/perf/pr_scoped_probes.json`.
That probe already includes focused `test_command`, `coverage_command`, and
`probe_command` entries for the native-MTP loader, regression tests, and the
JSON-emitting performance probe script.

## Slice plan

1. Keep the existing scandir and index-filtering behavior unchanged.
2. Narrow the implementation to local bindings for repeated string helper calls
   in `_extra_mtp_safetensor_file_paths(...)` so the hot loop avoids repeated
   attribute lookup while scanning large native-MTP index maps.
3. Reuse the existing native-MTP regression tests and changed-scope coverage
   command from the registered probe.
4. Run the registered probe locally on Linux before opening the PR. GitHub
   Actions PR-scoped performance remains the merge gate for the registered probe
   report.

## Validation boundary

This slice changes Python worker code only. Linux local validation covers the
Python regression tests, changed-scope coverage, and registered probe command.
No Swift/macOS runtime effect is claimed for this slice.
