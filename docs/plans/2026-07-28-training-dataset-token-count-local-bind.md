# Training dataset prompt/completion token counter local binding

## Scope

This Python-only performance slice is limited to
`_collect_prompt_completion_token_counts()` in
`services/mlx-worker-python/worker/model_ops/training_dataset.py`.
Prompt/completion quality summaries keep the same whitespace token-counting
semantics while avoiding repeated global helper lookup inside the hot loop.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`training-dataset-token-percentiles-single-sort` in
`infra/perf/pr_scoped_probes.json`. The probe watches `training_dataset.py` and
has focused `test_command`, `coverage_command`, and `probe_command` entries.
It is runnable locally on Linux and remains the CI merge gate for this slice.

## Plan

1. Bind `_whitespace_token_count` once before the prompt/completion token-count
   loop.
2. Preserve all accumulated token count, sum, and percentile outputs.
3. Run the registered focused tests, changed-scope coverage command, and local
   registered probe before opening the PR.
4. Merge only after GitHub Actions and the registered PR-scoped performance
   report complete successfully.

## Acceptance

- Focused training dataset tests pass locally.
- Changed-scope coverage for the touched Python scope is at least 95%.
- The registered local probe reports directionally lower elapsed time without
  changing duplicate/dirty/sample counts.
- CI PR-scoped performance validates the same registered probe before merge.
