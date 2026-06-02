# LoRA quantized-kind substring gate

## Scope

This Python-only performance slice is limited to `worker.model_ops.lora_runtime_metadata._quantized_kind_from_text()`. The helper still uses the precompiled boundary-aware regex patterns for correctness, but now skips the regex search when the candidate quantized-kind token is not present in the normalized input string.

The optimization targets repeated quantized-base detection in LoRA receipt/runtime metadata where most candidate identity strings do not contain every supported quantized-kind token.

## Registered probe

Registered PR-scoped probe: `lora-aux-modules-scandir` in `infra/perf/pr_scoped_probes.json`.

The probe already covers `services/mlx-worker-python/worker/model_ops/lora_runtime_metadata.py` and provides focused `test_command`, `coverage_command`, and `probe_command` entries. It reports the quantized-kind parser workload through `quantized_kind_baseline_elapsed_ms_mean`, `quantized_kind_optimized_elapsed_ms_mean`, `quantized_kind_delta_ms`, and `quantized_kind_iteration_count`, while retaining the existing auxiliary-module scandir and processor-resume metrics for the same module.

## Verification

Run the registered focused pytest command, changed-scope coverage, `git diff --check`, and the registered `lora-aux-modules-scandir` probe locally on Linux before opening the PR. PR-scoped performance CI remains the merge gate for the registered probe report.
