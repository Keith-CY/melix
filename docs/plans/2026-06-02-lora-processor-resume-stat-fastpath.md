# LoRA processor resume mode stat fast path slice

## Scope

Optimize the LoRA canary receipt `_processor_resume_mode` hot path in
`services/mlx-worker-python/worker/model_ops/lora_runtime_metadata.py`.

The current implementation checks three known resume asset filenames with
separate `Path` construction and `Path.is_file()` calls. The slice keeps the
same precedence (`processor_config.json`, then `preprocessor_config.json`, then
`tokenizer_config.json`) while using a module-level filename table, one
`os.fspath()` conversion, local `os.path.join`/`os.path.isfile` bindings, and no
per-check `Path` object construction.

## Registered Probe

Registered PR-scoped probe: `lora-aux-modules-scandir`.

The registry entry covers the affected LoRA runtime metadata module and provides
focused `test_command`, `coverage_command`, and `probe_command` values. This
slice extends the probe script and metrics to report processor resume mode
baseline/optimized latency and `os.path.isfile` call counts alongside the
existing auxiliary-module and quantized-kind measurements.

## Verification Plan

- Add focused tests for processor resume mode precedence, `os.path.isfile` usage,
  and missing-asset fallback.
- Run the registered focused `test_command` locally on Linux.
- Run the registered changed-scope `coverage_command` locally on Linux.
- Run the registered `probe_command` locally on Linux and compare before/after
  processor resume mode metrics.

## Expected Metrics

The probe should preserve behavior and reduce per-call overhead by avoiding
repeated `Path` object construction while keeping the same bounded three-file
existence check.
