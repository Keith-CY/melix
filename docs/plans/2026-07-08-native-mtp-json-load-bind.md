# Native MTP Loader JSON Load Bindings

## Scope

This Python-only performance slice is limited to the native-MTP loader's
`model.safetensors.index.json` payload read in
`services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py`.
It preserves the existing behavior: missing, unreadable, invalid, or non-object
index payloads still produce an empty mapping, and sidecar shard discovery keeps
its existing filtering, duplicate handling, missing-shard warnings, and base
`model*.safetensors` exclusion semantics.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`native-mtp-loader-safetensor-scandir` in `infra/perf/pr_scoped_probes.json`.
The registry entry already includes focused `test_command`, `coverage_command`,
and `probe_command` entries covering the native-MTP loader, its regression tests,
and the JSON-emitting performance probe script.

## Slice plan

1. Keep the sidecar shard discovery algorithm unchanged.
2. Bind the module-level binary-open helper and JSON loader used by
   `_load_json_payload(...)` so repeated native-MTP index reads avoid global
   builtins and module attribute lookups.
3. Reuse the existing native-MTP regression tests and changed-scope coverage
   command from the registered probe.
4. Run the registered probe locally on Linux before opening the PR. GitHub
   Actions PR-scoped performance remains the merge gate for the registered probe
   report.

## Validation boundary

This slice changes Python worker code only. Linux local validation covers the
Python regression tests, changed-scope coverage, and registered probe command.
No Swift/macOS runtime effect is claimed for this slice.
