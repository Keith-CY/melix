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
3. Cache ignored duplicate base `model*.safetensors` file names in the existing
   sidecar duplicate set. This keeps the sidecar result unchanged, but avoids
   repeating basename checks when large native-MTP indexes contain repeated
   MTP-prefixed references to ordinary base shards.
4. Reuse the existing native-MTP regression tests and changed-scope coverage
   command from the registered probe.
5. Run the registered probe locally on Linux before opening the PR. GitHub
   Actions PR-scoped performance remains the merge gate for the registered probe
   report.

## Validation boundary

This slice changes Python worker code only. Linux local validation covers the
Python regression tests, changed-scope coverage, and registered probe command.
No Swift/macOS runtime effect is claimed for this slice.

## Follow-up Slice: Nested Base Shard Prefix Check

The 2026-07-19 follow-up keeps the same registered probe and narrows to nested
base-shard filtering inside `_extra_mtp_safetensor_file_paths(...)`. The sidecar
scanner already rejects top-level and nested `model*.safetensors` base shards
before path existence checks. This slice preserves that behavior but checks the
nested basename with `str.startswith(..., start)` instead of slicing the basename
segment first, avoiding a short string allocation for repeated nested base-shard
references in large native-MTP weight maps.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass with non-regressive or improved elapsed time, and if
the PR-scoped CI probe completes successfully before merge.
