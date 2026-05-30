# Deterministic VLM Completion Token Count Cache

## Scope

This slice targets the registered `deterministic-vlm-completion-token-scan` PR-scoped performance probe. The affected runtime path is `services/mlx-worker-python/worker/runtime/deterministic_vlm_runtime.py`.

## Optimization

The deterministic VLM runtime repeatedly emits the same deterministic response text for repeated requests in probe and smoke-test paths. Completion token accounting previously rescanned that response on every emission. This slice caches the most recent completion response text and token count per runtime instance, preserving whitespace token semantics while eliding repeated scans for identical consecutive responses.

## Verification

The registered probe remains `scripts/deterministic_vlm_completion_token_probe.py` and reports:

- `elapsed_ms_mean`
- `split_calls_mean`
- `token_count_calls_mean`
- `peak_bytes_mean`
- `completion_tokens`

Focused tests cover both behavior parity and cache invalidation when the response text changes.
