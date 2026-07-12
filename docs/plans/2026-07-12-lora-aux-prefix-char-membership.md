# LoRA Auxiliary Prefix Character Membership Performance Slice

## Context

The registered PR-scoped probe `lora-aux-modules-scandir` covers
`services/mlx-worker-python/worker/model_ops/lora_runtime_metadata.py`, including
LoRA canary receipt construction, auxiliary module detection, processor resume
asset precedence, and quantized-kind parsing. The auxiliary module detector scans
base model directories once with `os.scandir` and filters candidate filenames by
first character, `.py` suffix, and known auxiliary prefixes.

## Slice

Replace the repeated inline first-character equality chain in
`_aux_modules_restored()` with a module-level prefix-character constant and a
single membership check. This keeps the same candidate set (`modeling_`,
`configuration_`, `tokenization_`, and `processing_`) while reducing branch work
in the per-entry scan loop.

The slice does not change processor resume precedence, JSON loading,
quantized-kind parsing, receipt fields, or the one-`scandir` directory traversal
contract.

## Probe

Registered probe: `lora-aux-modules-scandir`

Required local Linux validation:

- Focused LoRA training receipt tests for auxiliary module detection and related
  sidecar behavior.
- Changed-scope coverage for the LoRA metadata path and registered probe tests.
- `scripts/lora_aux_modules_scandir_probe.py` through the registered
  `command_json` probe path.

## Expected Impact

This should slightly lower `elapsed_ms_mean` for auxiliary module detection on
large noisy base model directories while preserving `scandir_calls_mean == 1` and
unchanged peak allocation behavior.
