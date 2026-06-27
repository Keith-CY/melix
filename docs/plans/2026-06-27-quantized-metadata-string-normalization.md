# Quantized metadata string normalization slice

## Scope

This Python-only performance slice is limited to the quantized tensor metadata
construction path in `worker.runtime.quantized_tensor_metadata`.

The behavior contract stays unchanged: metadata still drops empty tensor names,
coerces tensor names and shard names to strings, returns immutable
`MappingProxyType` metadata, and preserves index/header-derived shard lookup
semantics.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`quantized-tensor-metadata-prepass` in `infra/perf/pr_scoped_probes.json`.
The entry already has focused `test_command`, `coverage_command`, and
`probe_command` entries for the quantized metadata module, native MTP/VLM tests,
PR-scoped performance tests, and `scripts/quantized_tensor_metadata_prepass_probe.py`.

This slice uses the existing registered metrics, especially:

- `index_elapsed_ms_mean`
- `index_peak_bytes_mean`
- `header_elapsed_ms_mean`
- `header_peak_bytes_mean`
- `metadata_tensor_count`
- `header_tensor_count`

## Plan

1. Add a regression guard for single-pass string coercion while preserving empty
   tensor-name filtering and immutable metadata semantics.
2. Normalize tensor names once when building metadata mappings instead of
   calling `str(name)` repeatedly in comprehensions.
3. Run the registered focused test command, changed-scope coverage command, and
   registered probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the merge gate.

## Success criteria

- Focused quantized/native-MTP/VLM tests and PR-scoped registry tests pass.
- Changed-scope coverage remains at or above the repository threshold for touched files.
- The registered probe reports non-regression or improvement for index/header
  metadata construction metrics while preserving tensor-count guardrails.
