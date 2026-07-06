# Quantized metadata index direct binary open

## Scope

This Python-only performance slice is limited to the two `model.safetensors.index.json` helpers used by native-MTP and quantized tensor metadata prepass code:

- `worker.runtime.native_mtp.mlx_lm_loader._load_json_payload(...)`
- `worker.runtime.quantized_tensor_metadata._load_json_payload(...)`

The behavior contract stays unchanged: missing files, invalid JSON, OS read errors, and non-object payloads still return an empty mapping, while valid object payloads are returned unchanged.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `quantized-tensor-metadata-prepass` in `infra/perf/pr_scoped_probes.json`.

The registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries for the quantized metadata path. This slice uses the existing `index_elapsed_ms_mean` and `index_peak_bytes_mean` metrics as the primary local and CI performance signal, with header and metadata-decision metrics retained as regression guards.

## Plan

1. Add a regression guard proving the index JSON helpers avoid both text decoding and the `Path.read_bytes()` wrapper on the index hot path.
2. Replace `Path.read_bytes()` with direct binary `open(..., "rb")` plus `json.loads(...)` to reduce pathlib wrapper overhead while preserving exception handling.
3. Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the merge gate.

## Success criteria

- Focused quantized/native-MTP/VLM tests and PR-scoped registry tests pass.
- Changed-scope coverage remains at or above the repository threshold for touched files.
- The registered probe reports non-regression or improvement for `index_elapsed_ms_mean`, with existing quantized metadata metrics preserved.
