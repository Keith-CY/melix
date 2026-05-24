# Issue 1530 Training Runtime Preflight Implementation Plan

## Goal

Add LoRA training runtime dependency preflights and nested-failure cleanup
guards without expanding the managed artifact, offline, or cache integrity
scope owned by #1258.

## Architecture

The Python worker will record a small, import-safe runtime preflight receipt
before training starts. The preflight uses Python import metadata and platform
inspection only, so training inspection and text-only LoRA metadata paths remain
usable on non-Apple or dependency-limited hosts without importing execution-only
MLX runtimes.

Failure cleanup will live around the training call in `LoRATrainingPipeline`.
If native training or adapter audit raises, the pipeline clears traceback
references, runs garbage collection, optionally probes retained MLX tensor bytes
when MLX is already importable, and attaches bounded cleanup evidence to
`ModelOperationError.details`.

## Scope Boundaries

- Include: `runtime_gate`, `inspection_only_import`,
  `media_decoder_dependency`, `native_load_status`, `disabled_decoder_paths`,
  `fallback_reader`, `unsupported_reason`, `traceback_cleanup_result`, and
  `retained_tensor_bytes_after_failure`.
- Include: optional media decoder states `healthy`, `missing`, and `broken`.
- Include: text-only LoRA behavior staying unaffected when optional decoder
  dependencies are broken.
- Exclude: managed artifact cache integrity, offline/resume policy, artifact
  hash verification, or cache receipt expansion owned by #1258.

## Files

- Modify: `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`
  - Add import-safe preflight helpers.
  - Attach preflight fields to successful adapter manifests.
  - Attach cleanup evidence to training and audit failures.
- Modify: `services/mlx-worker-python/tests/test_lora_model_ops_unit.py`
  - Add focused red-green tests for dependency-limited inspection, media
    decoder state classification, text-only unaffected behavior, native load
    status fields, and nested-exception cleanup evidence.

## Test Plan

1. Add failing unit tests in `test_lora_model_ops_unit.py`.
2. Run the new pytest filter and verify the tests fail for missing fields or
   helpers.
3. Implement the minimal production code in `lora_training_pipeline.py`.
4. Re-run the focused pytest filter.
5. Run the broader LoRA unit file if focused tests pass quickly.
6. Run `git diff --check`.

## Performance Probes And Metrics

Preflight work runs once per LoRA training job before backend execution. The
probe performs bounded `importlib.util.find_spec` checks and optional GC cleanup
only on failure. Success metric: focused unit tests prove text-only training
does not fail when optional media decoders are broken, and failure metrics report
bounded retained tensor bytes where measurable.
