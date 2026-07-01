# Quantized metadata high-precision prefilter

## Scope

This Python-only performance slice is limited to the native multimodal
high-precision decision helper in
`services/mlx-worker-python/worker/runtime/quantized_tensor_metadata.py`.

The behavior contract stays unchanged: high-precision decisions remain based on
segment boundaries for vision/audio/projector/output modules, and similarly named
non-segments such as `prevision_tower`, `visualizer`, and
`output_projection` must still return false.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`quantized-tensor-metadata-prepass` in `infra/perf/pr_scoped_probes.json`.
The probe already has focused `test_command`, `coverage_command`, and
`probe_command` entries for this path. This slice uses
`high_precision_decision_elapsed_ms_mean` and
`high_precision_decision_peak_bytes_mean` as the primary performance signal,
with the rest of the registered quantized metadata metrics as regression guards.

## Plan

1. Reuse the existing boundary regression coverage in
   `test_native_multimodal_high_precision_module_segment_scan_preserves_boundaries`.
2. Add a cheap substring prefilter before the segment scanner so common language
   model prefixes without any high-precision marker can return immediately.
3. Keep the segment scanner as the source of truth for positive and near-miss
   strings so boundary behavior does not drift.
4. Run the registered focused test command, changed-scope coverage command, and
   registered probe locally on Linux before opening the PR.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Success criteria

- Focused quantized/native-MTP/VLM tests and PR-scoped registry tests pass.
- Changed-scope coverage remains at or above the repository threshold for touched
  files.
- The registered probe reports improvement for
  `high_precision_decision_elapsed_ms_mean` while preserving decision counts.
