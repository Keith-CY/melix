# OCR single-image token-count clamp fast path

## Goal

Reduce overhead in `DeterministicOCRRuntime.prompt_token_count()` for the common OCR path: one inline image, no videos, and precomputed `preprocess_input_bytes`.

## Scope

- Keep OCR prompt-token semantics unchanged.
- Touch only `services/mlx-worker-python/worker/runtime/deterministic_ocr_runtime.py` and this plan.
- Reuse the registered PR-scoped probe `deterministic-ocr-token-count-scan`.

## Registered probe

`infra/perf/pr_scoped_probes.json` already registers `deterministic-ocr-token-count-scan` with focused `test_command`, `coverage_command`, and `probe_command` entries. Its `probe_command` runs `scripts/deterministic_ocr_token_count_probe.py`; the primary slice metric is `elapsed_ms_mean` over repeated `prompt_token_count()` calls.

## Implementation plan

1. Preserve the cached whitespace prompt-token count behavior.
2. Keep the single-image/no-video fast path based on precomputed `preprocess_input_bytes`.
3. Replace the branchy minimum-token clamp with an expression clamp in the return path, avoiding a mutable local update on the hot path.
4. Run the registered focused tests, changed-scope coverage, and local Linux registered probe before opening the PR.

## Validation boundary

This is a Python runtime slice and is locally verifiable on Linux. CI remains required for the registered PR-scoped performance report before merge.
