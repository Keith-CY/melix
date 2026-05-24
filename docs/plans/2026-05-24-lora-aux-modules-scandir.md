# LoRA Auxiliary Module Scandir Slice

## Goal

Reduce filesystem iterator overhead in LoRA canary receipt generation when checking
whether a base model directory restored auxiliary Python modules (`modeling_*.py`,
`configuration_*.py`, `tokenization_*.py`, or `processing_*.py`).

## Scope

- Path: `services/mlx-worker-python/worker/model_ops/lora_runtime_metadata.py`
- Replace the current four `Path.glob(...)` probes with one direct
  `os.scandir(...)` pass over the base model directory.
- Preserve the existing direct-child filename contract for auxiliary module
  detection.
- Register a PR-scoped probe for this path so CI and local verification can
  compare the changed hot path.

## Probe

Registered probe: `lora-aux-modules-scandir`

Metrics:

- `elapsed_ms_mean` (lower is better)
- `peak_bytes_mean` (lower is better)
- `scandir_calls_mean` (lower is better; expected `1.0` per sample)
- `noise_file_count` (input scale)

## Verification Plan

1. Focused regression tests for complete and missing LoRA canary resume assets.
2. New regression test proving auxiliary module detection uses one `os.scandir`
   pass and does not call `Path.glob`.
3. Changed-scope coverage command from the registered probe.
4. Registered probe locally on Linux before opening the PR.
5. PR-scoped performance workflow in GitHub Actions before merge.

## Linux Boundary

This slice changes Python worker metadata code and is locally verifiable on
Linux. No Swift/macOS-only runtime effect is claimed for this slice.
