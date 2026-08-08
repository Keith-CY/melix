# Quantized high-precision decision cache performance slice

## Scope

This Python performance slice is limited to the native multimodal high-precision
module classifier in `worker.runtime.quantized_tensor_metadata`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`quantized-tensor-metadata-prepass` in `infra/perf/pr_scoped_probes.json`. The
registry entry already includes focused `test_command`, `coverage_command`, and
`probe_command` entries for the quantized metadata path and its synthetic probe.

## Optimization plan

Native multimodal quantization calls `_native_multimodal_high_precision_module()`
for repeated module prefixes during metadata and materialized-weight decisions.
The helper is pure for a normalized prefix string, so this slice memoizes its
boolean result with a bounded `lru_cache`. The existing segment-boundary
regression coverage continues to verify behavior, while the registered probe
warms the cache before the repeated-decision measurement so the metric captures
steady-state request-loop reuse rather than one-time cache population allocation.

Behavior remains unchanged: callers still normalize request prefixes before this
helper, exact segment boundaries are preserved, and tensor metadata parsing is not
altered.

## Verification

Local Linux validation must run:

1. The registered focused tests for `quantized-tensor-metadata-prepass`.
2. The registered changed-scope coverage command.
3. The registered local probe command.

GitHub Actions PR-scoped performance remains the final registered probe merge
gate.

## Expected metrics

The primary expected direction is lower `high_precision_decision_elapsed_ms_mean`
in the registered probe. Index/header parsing and tensor-name membership metrics
should remain within warning thresholds because this slice only caches the pure
high-precision classifier.
