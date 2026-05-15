# Rerank top-k=1 max-index scan performance slice

## Scope

This slice keeps rerank ordering semantics unchanged while tightening the bounded
`top_k=1` fast path in `RerankCore._rank_scores`.

## Probe coverage

The affected path is already covered by the registered PR-scoped probe
`rerank-core-top-k-heap-selection` in `infra/perf/pr_scoped_probes.json`. That
entry includes focused `test_command`, `coverage_command`, and `probe_command`
commands and watches:

- `services/mlx-worker-python/worker/engine/rerank_core.py`
- `services/mlx-worker-python/tests/test_rerank_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/rerank_top_k_probe.py`

## Implementation plan

- Preserve the existing full-sort and bounded heap behavior for `top_k` values
  other than one.
- Replace the Python-level manual best-score loop for `top_k=1` with the built-in
  `max(range(len(scores)), key=scores.__getitem__)`, which keeps first-index
  tie-breaking while moving the comparison loop into the built-in implementation.
- Reuse existing rerank regression tests and the registered probe to validate
  behavior and performance.

## Validation

Local Linux validation must include:

- focused rerank test command from the registered probe
- changed-scope coverage command from the registered probe
- `scripts/rerank_top_k_probe.py` probe command

The CI PR-scoped performance workflow remains the merge gate for the registered
probe report.
