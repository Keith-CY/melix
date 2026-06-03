# LoRA quantized kind strip elision slice

This Python-only performance slice is limited to the quantized-base kind parser in `services/mlx-worker-python/worker/model_ops/lora_runtime_metadata.py`.

## Registered probe coverage

The affected path is covered by the registered PR-scoped performance probe `lora-aux-modules-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/lora_runtime_metadata.py`
- `services/mlx-worker-python/tests/test_lora_training_receipts.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/lora_aux_modules_scandir_probe.py`

No registry change is required for this slice.

## Optimization slice

`_quantized_kind_from_text()` lowercases and scans candidate model identity text for quantization markers such as `q4`, `4bit`, and `optiq`. The compiled boundary regex already treats leading and trailing whitespace as non-alphanumeric delimiters, so this slice removes the redundant full-string `strip()` before `lower()`.

The behavior remains unchanged for whitespace-padded values and embedded suffix false positives; the focused regression test now asserts a whitespace-padded `q8` marker still resolves correctly.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and the registered local probe on Linux before opening the PR. The PR-scoped performance workflow remains the merge gate for the registered probe result in CI.

## Expected metrics

The registered probe reports quantized-kind parser metrics:

- `quantized_kind_baseline_elapsed_ms_mean`
- `quantized_kind_optimized_elapsed_ms_mean`
- `quantized_kind_delta_ms`
- `quantized_kind_iteration_count`

The slice is accepted only if local probe and CI evidence show no regression and preferably a lower optimized quantized-kind elapsed mean.
