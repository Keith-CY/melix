# Deterministic rerank contiguous-query scan

## Scope

This performance slice keeps deterministic rerank scoring semantics unchanged and narrows the default Jina v3 / causal-lm hot path inside `worker/runtime/rerank_backends.py`.

The contiguous-query bonus previously sliced the document token sequence for every possible start offset. This slice checks the first query token before building a candidate slice and reuses the query length inside the loop. The optimization reduces per-document slice allocation when the first query token is absent or sparse in long candidate documents while preserving exact contiguous-query matching semantics.

## Registered probe

The affected path is covered by the existing PR-scoped probe `deterministic-rerank-query-context-reuse` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- `test_command` for focused rerank runtime tests and probe selection/dispatch tests.
- `coverage_command` for changed-scope coverage across rerank runtime/backends, PR-scoped performance support, and focused tests.
- `probe_command` that measures repeated deterministic rerank scoring for 2,048 documents and reports elapsed time plus context-build/tokenize counters.

## Verification plan

Run the registered commands locally on Linux:

1. Focused tests from the registered probe.
2. Changed-scope coverage from the registered probe.
3. Registered probe command and compare against the pre-change baseline.

CI remains the merge gate for the registered PR-scoped performance workflow.

## Metrics

Baseline probe before this slice on the isolated Linux worktree:

```json
{"document_count": 2048.0, "elapsed_ms_mean": 84.314528, "iteration_count": 8.0, "query_context_builds_mean": 1.0, "sample_count": 5.0, "tokenize_calls_mean": 2049.0}
```

Post-change metrics are recorded in the PR evidence after the local registered probe run.
