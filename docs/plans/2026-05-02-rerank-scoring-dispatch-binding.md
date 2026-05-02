# Deterministic Rerank Tie-Breaker Cache

## Scope

This slice keeps deterministic rerank scoring semantics unchanged while narrowing a Python hot path in the rerank runtime. Deterministic tie-breaker values are pure functions of `(query, document)` but are recomputed for every repeated score call. This slice adds a bounded cache to `DeterministicRerankBackend.tie_breaker`, binds the family scoring method once per request before the per-document loop, and reuses the already-computed query token-set length inside family overlap math.

## Affected paths

- `services/mlx-worker-python/worker/runtime/deterministic_rerank_runtime.py`
- `services/mlx-worker-python/worker/runtime/rerank_backends.py`
- `services/mlx-worker-python/tests/test_rerank_runtime.py`

## Registered probe

The affected path is covered by registered PR-scoped probe `deterministic-rerank-query-context-reuse` in `infra/perf/pr_scoped_probes.json`.

The registered probe includes:

- `test_command` for focused rerank runtime tests and PR-scoped probe selection/dispatch tests.
- `coverage_command` for changed-scope coverage across rerank runtime/backends, PR-scoped performance support, and focused tests.
- `probe_command` measuring repeated deterministic rerank scoring for 2,048 documents and reporting elapsed time plus context-build/tokenize counters.

## Validation plan

Run the registered focused test, changed-scope coverage, and probe commands locally on Linux. CI remains the source of truth for the PR-scoped registered probe report after the PR is opened.
