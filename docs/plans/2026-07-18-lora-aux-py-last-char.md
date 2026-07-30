# LoRA Auxiliary Module `.py` Suffix Last-Character Guard

## Context

The registered PR-scoped probe `lora-aux-modules-scandir` covers LoRA runtime metadata auxiliary module detection in `worker.model_ops.lora_runtime_metadata`. The registry entry already provides focused `test_command`, `coverage_command`, and `probe_command` entries for the affected path.

`_aux_modules_restored()` scans base-model directory entries and filters likely auxiliary Python sidecars by first-character prefix, `.py` suffix, and full auxiliary prefix. On noisy directories, most candidates are not Python files. This slice adds a cheap final-character guard before the full `.endswith(".py")` suffix check so non-`.py` entries can skip the full suffix comparison while preserving the existing prefix and suffix semantics.

## Scope

- Limit behavior change to `_aux_modules_restored()` in `services/mlx-worker-python/worker/model_ops/lora_runtime_metadata.py`.
- Keep the single `os.scandir()` pass and existing `OSError` fallback behavior.
- Do not change processor-resume or quantized-kind detection behavior covered by the same registered probe.

## Measurement

Registered probe: `lora-aux-modules-scandir`

Required local Linux commands:

- Focused registry test command for `lora-aux-modules-scandir`.
- Changed-scope coverage command for the same registry entry.
- Registered probe command from `infra/perf/pr_scoped_probes.json`.

Success requires focused behavior tests to pass, changed-scope coverage to remain at or above 95%, and the local registered probe to show directional improvement or no regression for the auxiliary-module scandir metric. GitHub Actions PR-scoped performance remains the merge gate after push.

## Linux Boundary

This is a Python worker path and can be validated locally on Linux. CI remains the source of truth for the registered PR-scoped performance report after the PR is opened.
