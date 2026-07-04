# Quantized metadata string normalization slice

## Scope

This Python-only performance slice is limited to `worker.runtime.quantized_tensor_metadata.QuantizedTensorMetadata` construction and `quantized_tensor_metadata_from_index_payload(...)` string normalization.

The behavior contract stays unchanged: tensor names and shard identifiers are normalized with `str(...)`, empty tensor names are ignored, the resulting mapping remains immutable, and index payloads without a mapping `weight_map` still return `EMPTY_QUANTIZED_TENSOR_METADATA`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `quantized-tensor-metadata-prepass` in `infra/perf/pr_scoped_probes.json`.

The probe entry has focused `test_command`, `coverage_command`, and `probe_command` entries for the quantized metadata path. This slice uses the existing `index_elapsed_ms_mean` and `index_peak_bytes_mean` metrics as the primary performance signal, while keeping the existing header and decision metrics as regression guards.

## Plan

1. Add a regression test that verifies non-string tensor names and shard identifiers are normalized once into the immutable metadata mapping.
2. Replace duplicate `str(tensor_name)` conversions in metadata construction with local normalized values while preserving empty-name filtering.
3. Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the merge gate.

## Success criteria

- Focused quantized/native-MTP/VLM tests and PR-scoped registry tests pass.
- Changed-scope coverage remains at or above the repository threshold for touched files.
- The registered probe reports non-regression or improvement for `index_elapsed_ms_mean` with existing quantized metadata metrics preserved.
