# Rerank Order Check Reuse Optimization

## Goal

Reduce redundant query-order scans in the deterministic rerank scoring path on Linux-verifiable Python code.

## Scope

Touched files:

- `services/mlx-worker-python/worker/runtime/rerank_backends.py`
- `services/mlx-worker-python/tests/test_rerank_runtime.py`

## Linux-only constraint

This slice is Python-only and can be verified locally on Linux with focused pytest, changed-scope coverage, and the existing PR-scoped performance probe.

## Performance probe

Probe ID: `deterministic-rerank-query-context-reuse`

The existing probe watches `rerank_backends.py` and exercises 2,048 deterministic rerank documents over repeated samples. Success means preserving the existing `query_context_builds_mean=1.0` and `tokenize_calls_mean=2049.0` metrics while improving or not regressing `elapsed_ms_mean` compared with `origin/main`.

## Implementation plan

1. Route Jina v3 exact-order and prefix checks through `_query_order_matches(...)` once when all query terms overlap.
2. Route CausalLM exact-order and prefix checks through the same helper once under the same condition.
3. Add focused regression tests that fail if full-overlap scoring bypasses the combined order helper and separately calls the lower-level contiguous/prefix helpers.
4. Run focused tests, changed-scope coverage, `git diff --check`, and the existing scoped probe locally.

## Success metrics

- Focused rerank tests pass.
- Changed executable line coverage is at least 95%.
- Local probe reports concrete numbers and preserves score output shape/metrics.
