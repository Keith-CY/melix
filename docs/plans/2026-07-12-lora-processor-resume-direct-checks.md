# LoRA Processor Resume Direct Checks Performance Slice

## Context

The registered PR-scoped probe `lora-aux-modules-scandir` covers
`services/mlx-worker-python/worker/model_ops/lora_runtime_metadata.py`, including
LoRA canary receipt construction, auxiliary module detection, processor resume
asset precedence, and quantized-kind parsing. The existing processor resume path
checks three known sidecar filenames in priority order for each canary receipt.

## Slice

Replace the tiny tuple-driven processor resume filename loop with direct ordered
`os.path.isfile` checks. This keeps the same precedence:

1. `processor_config.json`
2. `preprocessor_config.json`
3. `tokenizer_config.json`
4. `missing`

The slice does not change auxiliary module detection, JSON loading, quantized-kind
parsing, or receipt fields.

## Probe

Registered probe: `lora-aux-modules-scandir`

Required local Linux validation:

- Focused LoRA training receipt tests for processor resume and canary receipt behavior.
- Changed-scope coverage for the LoRA metadata path and registered probe tests.
- `scripts/lora_aux_modules_scandir_probe.py` through the registered `command_json`
  probe path.

## Expected Impact

This should shave per-call overhead from the processor resume hot path by avoiding
loop tuple unpacking and repeated generic filename dispatch while preserving the
same ordered filesystem checks.
