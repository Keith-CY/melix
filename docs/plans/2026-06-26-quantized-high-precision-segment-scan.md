# Quantized high-precision segment scan slice

## Scope

This Python-only performance slice is limited to `worker.runtime.quantized_tensor_metadata._native_multimodal_high_precision_module(...)`, which runs during native multimodal quantization decisions to decide whether vision/projector/output modules should keep their exported precision unless explicit quantized scale metadata is present.

The behavior contract stays unchanged: dot-separated module path segments are matched exactly, empty dot segments are ignored, `model`/`language_model` containers still allow the following high-precision segment to match, and partial segment names such as `visualizer` or `output_projection` do not match.

## Registered probe

The affected path is covered by the registered PR-scoped probe `quantized-tensor-metadata-prepass` in `infra/perf/pr_scoped_probes.json`.

This slice extends that registered probe with focused high-precision decision metrics:

- `high_precision_decision_elapsed_ms_mean`
- `high_precision_decision_peak_bytes_mean`
- `high_precision_decision_count`

The probe entry already has focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/quantized_tensor_metadata.py`
- `services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py`
- `services/mlx-worker-python/worker/runtime/mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/quantized_tensor_metadata_prepass_probe.py`

## Plan

1. Add a regression test that preserves exact segment-boundary behavior for high-precision module detection.
2. Replace tuple materialization from `prefix.split(".")` with a single-pass dot-segment scan and module-level segment sets.
3. Extend the registered probe and registry metrics so PR-scoped performance directly measures the affected high-precision decision path.
4. Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Success criteria

- Focused quantized/native-MTP/VLM tests and PR-scoped registry tests pass.
- Changed-scope coverage remains at or above the repository threshold for touched files.
- The registered probe reports non-regression or improvement for the new high-precision decision metric while preserving existing quantized metadata metrics.

## Follow-up slice: empty materialized-weight fast path

A later Python-only performance slice keeps the same registered probe and narrows the changed behavior to `quantized_scales_present(...)` when callers pass an empty materialized `weights` mapping. In metadata-prepass decision loops, the quantized scale answer is already fully determined by `QuantizedTensorMetadata`, so the helper can skip the redundant `scales_key in weights` lookup for empty mappings while preserving non-empty materialized-weight fallback behavior.

The `quantized-tensor-metadata-prepass` probe already covers this path through `metadata_decision_elapsed_ms_mean` and `metadata_decision_peak_bytes_mean`, with the existing focused `test_command`, `coverage_command`, and `probe_command` entries.

## Follow-up slice: safetensors header key normalization once

This Python-only follow-up stays inside `worker.runtime.quantized_tensor_metadata` and the registered `quantized-tensor-metadata-prepass` probe. The safetensors header parser now normalizes each non-`__metadata__` JSON key to `str` once before appending it to the returned tensor-name tuple. Behavior is unchanged for empty names and metadata entries, while the header scan avoids the previous generator expression's duplicate `str(key)` conversion in the hot header prepass.

Validation remains the focused registered test command, changed-scope coverage command, local Linux registered probe, and GitHub Actions PR-scoped performance report.
