# Retrieval Lookup List Copy Fast Path

## Summary

This Python-only performance slice keeps retrieval lookup projection behavior
unchanged and narrows one hot path in
`worker.runtime.retrieval_context._copy_payload_value`: small list payload copies.
Lookup payload metadata commonly contains empty, one-item, two-item, and
three-item lists, and the registered probe includes a three-item `scores` list in
each synthetic retrieved context.

## Registered probe

The affected path is already covered by the registered PR-scoped performance
probe `retrieval-context-projection-fastpath` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/retrieval_context_projection_probe.py`

No new probe registration is required for this slice.

## Optimization slice

Fast-path exact `list` payload copies for lengths 0, 1, 2, and 3 in the same
recursive helper that already fast-paths small tuples. Longer lists and unknown
value types keep the existing comprehension / `deepcopy` behavior.

## Validation plan

Run the registered focused tests, changed-scope coverage command, and registered
probe locally on Linux before pushing. GitHub Actions and the PR-scoped
performance workflow remain the merge gate before the PR is squash-merged.
