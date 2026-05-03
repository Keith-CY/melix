# Rerank Query Context Reuse Plan

## Goal

Reduce repeated query-side work in the deterministic rerank runtime by computing reusable query context once per rerank request and reusing it across all document scoring calls.

## Scope

- `services/mlx-worker-python/worker/runtime/deterministic_rerank_runtime.py`
- `services/mlx-worker-python/worker/runtime/rerank_backends.py`
- `services/mlx-worker-python/tests/test_rerank_runtime.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- optional probe script under `scripts/` if needed

## Linux Constraint

This cron run executes on Linux, so the implementation must remain Python-only and be fully verifiable with focused pytest, changed-scope coverage, and an explicit local performance probe. The PR-scoped performance registry must also include a focused probe for this rerank path.

## Optimization Hypothesis

`DeterministicRerankRuntime.score_documents()` already tokenizes the query once, but the rerank family adapters still derive additional query-side structures per document. Precomputing the reusable query context once per request should reduce repeated per-document work without changing ranking semantics.

## Task

1. Add a small immutable query-context container for reusable query-side derived values.
2. Thread that context through the rerank family adapters.
3. Add focused tests that fail before the optimization and prove the context is built once while scores remain stable.
4. Register a PR-scoped performance probe for the rerank path and cover it with focused probe tests.

## Performance Probe

- Probe ID: `deterministic-rerank-query-context-reuse`
- Path: PR-scoped performance registry plus probe implementation/helper
- Synthetic workload: run deterministic rerank scoring for one query against 2048 documents, repeated 8 times per sample across 5 samples to keep elapsed timing in a less noisy range while preserving per-request reuse metrics
- Metrics:
  - `elapsed_ms_mean` lower is better
  - `query_context_builds_mean` lower is better, target `1.0`
  - `tokenize_calls_mean` lower is better, target `documents + 1`
  - `document_count` informational

## Success Metrics

- No ranking or score regressions in focused rerank tests.
- Changed executable scope coverage >= 95%.
- Local probe shows `query_context_builds_mean == 1.0` and improved elapsed time versus the pre-change baseline.
- PR-scoped performance probe is registered and selected for rerank-path changes.

## Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_rerank_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_rerank_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/deterministic_rerank_runtime.py services/mlx-worker-python/worker/runtime/rerank_backends.py services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_rerank_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_deterministic_rerank_query_context_reuse as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"
git diff --check
```
