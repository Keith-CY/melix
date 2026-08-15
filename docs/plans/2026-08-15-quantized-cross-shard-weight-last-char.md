# Quantized Cross-Shard Weight Last-Character Guard

## Context

The registered PR-scoped probe `quantized-tensor-metadata-prepass` covers
`services/mlx-worker-python/worker/runtime/quantized_tensor_metadata.py`, including
index/header metadata prepass construction, quantized-scale decisions,
high-precision multimodal decisions, tensor-name cache access, and cached
cross-shard `.weight` / `.scales` fixup counts.

`_count_cross_shard_quantized_metadata_fixups()` scans normalized tensor names
once while metadata is constructed. Only `.weight` tensors can start a fixup
lookup, but noisy metadata maps also contain `.scales`, `.biases`, and other
non-weight keys. This slice adds a cheap final-character guard before the full
`.endswith(".weight")` suffix comparison so non-weight names that cannot end in
`.weight` skip the suffix check.

## Scope

- Limit behavior change to `_count_cross_shard_quantized_metadata_fixups()`.
- Preserve the cached count contract and direct mapping lookup behavior.
- Do not change index parsing, safetensors header parsing, quantized-scale
  decisions, high-precision multimodal decisions, or native-MTP loading.

## Measurement

Registered probe: `quantized-tensor-metadata-prepass`

Required local Linux commands:

- Focused registry test command for `quantized-tensor-metadata-prepass`.
- Changed-scope coverage command for the same registry entry.
- Registered probe command from `infra/perf/pr_scoped_probes.json`.

Success requires focused behavior tests to pass, changed-scope coverage to remain
at or above 95%, and the registered probe to show directional improvement or no
regression for the metadata decision / cross-shard fixup metrics. GitHub Actions
PR-scoped performance remains the merge gate after push.

## Linux Boundary

This is a Python worker path and can be validated locally on Linux. CI remains
the source of truth for the registered PR-scoped performance report after the PR
is opened.
