# LoRA Auxiliary Prefix Character Slice

This Python performance slice is limited to LoRA auxiliary module detection in
`services/mlx-worker-python/worker/model_ops/lora_runtime_metadata.py`.

## Scope

- Replace the per-entry `frozenset` membership check for auxiliary module prefix
  first characters with direct literal comparisons.
- Preserve the existing `os.scandir()` traversal, `.py` suffix requirement, and
  accepted auxiliary prefixes: `modeling_`, `configuration_`, `tokenization_`,
  and `processing_`.
- Keep the slice Python-only and locally verifiable on Linux.

## Registered Probe

The affected path is covered by the existing registered PR-scoped performance
probe `lora-aux-modules-scandir` in `infra/perf/pr_scoped_probes.json`. The probe
entry already includes focused `test_command`, `coverage_command`, and
`probe_command` fields for this module, including auxiliary scan metrics:

- `elapsed_ms_mean`
- `elapsed_ms_min`
- `peak_bytes_mean`
- `scandir_calls_mean`
- `noise_file_count`

## Verification Plan

Run the registered probe's focused tests, changed-scope coverage command, and
probe command locally on Linux before opening or updating the PR. GitHub Actions
PR-scoped performance remains the merge gate.
