# LoRA Quantized Kind Lowercase Fast Path

## Scope

Optimize the Python LoRA runtime metadata quantized-kind parser in
`services/mlx-worker-python/worker/model_ops/lora_runtime_metadata.py` by checking
already-lowercase quantization tokens before allocating a lowercase copy of the
input string.

## Probe Coverage

The affected path is covered by the registered PR-scoped probe
`lora-aux-modules-scandir` in `infra/perf/pr_scoped_probes.json`. The registry
entry includes focused `test_command`, `coverage_command`, and `probe_command`
entries for the LoRA runtime metadata module, receipt tests, PR-scoped
performance tests, and `scripts/lora_aux_modules_scandir_probe.py`.

## Behavior Contract

The parser keeps the existing boundary-regex semantics:

- lowercase quantized profile strings still return the matching kind;
- uppercase/mixed-case strings fall back to lowercase matching;
- embedded suffixes such as `not-a-q4suffix` remain `unknown`;
- the implementation still reuses the precompiled quantized-kind regex patterns.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and registered
`lora-aux-modules-scandir` probe locally on Linux. The local probe records the
optimized quantized-kind parser timing versus the probe baseline. PR-scoped CI
performance validation remains the merge gate.

The probe also emits sidecar within-probe delta metrics for the earlier processor
resume slice and this quantized-kind timing slice. Those deltas are retained as
diagnostic evidence only: the gated signals are the direct optimized elapsed
metrics and call-count guard rails, because tiny changes in a negative
optimized-minus-baseline delta can otherwise flag unrelated scheduler noise as a
regression.
