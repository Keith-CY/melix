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

### 2026-07-12 ASCII boundary follow-up

This follow-up keeps the same Python-only boundary and registered `lora-aux-modules-scandir` probe. The quantized-kind parser only needs the existing `(?<![a-z0-9])... (?![a-z0-9])` delimiter semantics, so it now uses direct `str.find()` plus ASCII lower-alphanumeric boundary checks instead of dispatching through compiled regex searches for each candidate kind. Behavior remains unchanged for lowercase, uppercase, whitespace-padded, hyphen-delimited, and non-ASCII-delimited markers, while substring false positives such as `not-a-q4suffix` remain rejected.

### 2026-07-18 boundary inline-ASCII follow-up

This follow-up stays inside the same parser and registered probe. `_quantized_kind_from_text()` keeps the fixed quantized-kind priority order but unrolls the tiny candidate set to avoid tuple iteration overhead on every LoRA metadata parse. `_contains_quantized_kind_token()` now evaluates the ASCII alphanumeric boundary checks inline after each `str.find()` hit, avoiding helper dispatch in the inner scan loop while preserving the existing direct-substring gate and delimiter semantics. The change keeps the case where an early embedded false-positive token such as `badq4` is skipped and a later delimited `q4` token is accepted.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and the registered local probe on Linux before opening the PR. For the ASCII boundary follow-up, compare the registered probe against `origin/main` locally; the PR-scoped performance workflow remains the merge gate for the registered probe result in CI.

For the 2026-07-18 follow-up, use the same `lora-aux-modules-scandir` registered probe locally on Linux and in PR-scoped performance CI. No registry change is required because the entry already watches the parser, focused tests, probe script, and this plan.

## Expected metrics

The registered probe reports quantized-kind parser metrics:

- `quantized_kind_baseline_elapsed_ms_mean`
- `quantized_kind_optimized_elapsed_ms_mean`
- `quantized_kind_delta_ms`
- `quantized_kind_iteration_count`

The slice is accepted only if local probe and CI evidence show no regression and preferably a lower optimized quantized-kind elapsed mean.
